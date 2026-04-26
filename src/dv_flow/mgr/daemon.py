#****************************************************************************
#* daemon.py
#*
#* Background daemon process managing a worker pool and accepting
#* task dispatch from dfm run clients over a Unix socket.
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Type

from .pool_manager import PoolManager, WorkerInfo
from .runner_config import RunnerConfig
from .worker_protocol import (
    METHOD_WORKER_REGISTER,
    METHOD_TASK_RESULT,
    METHOD_WORKER_HEARTBEAT,
    build_task_execute,
    build_task_cancel,
    build_worker_shutdown,
    encode_message,
    parse_message,
    ProtocolError,
)


_log = logging.getLogger("Daemon")

DAEMON_STATE_FILE = "daemon.json"
DAEMON_SOCKET_FILE = "daemon.sock"


class Daemon:
    """Background pool manager daemon.

    Listens for worker connections on a TCP port and client connections
    on a Unix socket.  When a task is dispatched to a worker (either
    immediately or when a worker becomes available), the daemon sends
    the ``task.execute`` message over the wire via a dispatch callback
    on the PoolManager.

    For the ``local`` runner the daemon forks ``dfm worker`` sub-
    processes that connect back on the TCP port.
    """

    def __init__(
        self,
        project_root: str,
        config: Optional[RunnerConfig] = None,
        backend_cls: Optional[Type] = None,
        worker_port: int = 0,
    ):
        self._project_root = project_root
        self._config = config or RunnerConfig()
        self._backend_cls = backend_cls
        self._worker_port = worker_port

        self._dfm_dir = os.path.join(os.path.realpath(project_root), ".dfm")
        self._socket_path = os.path.join(self._dfm_dir, DAEMON_SOCKET_FILE)
        self._state_path = os.path.join(self._dfm_dir, DAEMON_STATE_FILE)

        self._pool = PoolManager(
            config=self._config.pool,
            launch_worker_fn=self._launch_worker,
            kill_worker_fn=self._kill_worker,
            dispatch_fn=self._on_dispatch,
        )

        self._worker_server: Optional[asyncio.AbstractServer] = None
        self._client_server: Optional[asyncio.AbstractServer] = None
        self._monitor_writers: List[asyncio.StreamWriter] = []
        self._running = False
        self._resolved_worker_port = 0

        # Per-client write locks keyed by writer id, so background
        # response tasks can safely write to a client connection.
        self._client_write_locks: Dict[int, asyncio.Lock] = {}

        # Map request_id -> (msg_id, client_writer) so we can route
        # results back to the originating client asynchronously.
        self._inflight: Dict[str, tuple] = {}

    @property
    def pool(self) -> PoolManager:
        return self._pool

    @property
    def socket_path(self) -> str:
        return self._socket_path

    @property
    def state_path(self) -> str:
        return self._state_path

    @property
    def worker_port(self) -> int:
        return self._resolved_worker_port

    async def run(self):
        """Start daemon and run until shutdown."""
        os.makedirs(self._dfm_dir, exist_ok=True)

        self._worker_server = await asyncio.start_server(
            self._handle_worker, "0.0.0.0", self._worker_port
        )
        addr = self._worker_server.sockets[0].getsockname()
        self._resolved_worker_port = addr[1]
        _log.info("Worker listener on port %d", self._resolved_worker_port)

        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)
        self._client_server = await asyncio.start_unix_server(
            self._handle_client, path=self._socket_path
        )
        _log.info("Client listener on %s", self._socket_path)

        self._write_state_file()
        self._pool.start_idle_checker()
        self._running = True
        _log.info("Daemon started (pid=%d)", os.getpid())

        try:
            while self._running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await self._cleanup()

    async def shutdown(self):
        _log.info("Shutdown requested")
        self._running = False

    async def _cleanup(self):
        _log.info("Cleaning up...")
        await self._pool.shutdown()

        if self._worker_server:
            self._worker_server.close()
            await self._worker_server.wait_closed()
        if self._client_server:
            self._client_server.close()
            await self._client_server.wait_closed()
        for w in self._monitor_writers:
            try:
                w.close()
            except Exception:
                pass
        self._monitor_writers.clear()
        self._remove_state_file()
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except OSError:
                pass
        _log.info("Daemon stopped")

    # ---- worker connections ----

    async def _handle_worker(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        worker_id = None
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = parse_message(line.decode("utf-8"))
                except ProtocolError as e:
                    _log.warning("Worker protocol error: %s", e)
                    continue

                method = msg["method"]
                params = msg["params"]

                if method == METHOD_WORKER_REGISTER:
                    worker_id = params.get("worker_id", "")
                    info = WorkerInfo(
                        worker_id=worker_id,
                        resource_class=params.get("resource_class", ""),
                        hostname=params.get("hostname", ""),
                        pid=params.get("pid", 0),
                        lsf_job_id=params.get("lsf_job_id", ""),
                    )
                    info.writer = writer
                    self._pool.register_worker(info)
                    self._emit_event("worker.state", info.to_dict())

                elif method == METHOD_TASK_RESULT:
                    request_id = params.get("request_id", "")
                    if worker_id:
                        self._pool.complete_task(worker_id, request_id, params)
                        self._emit_event("task.completed", {
                            "request_id": request_id,
                            "worker_id": worker_id,
                            "status": params.get("status", 0),
                        })
                        w = self._pool.workers.get(worker_id)
                        if w:
                            self._emit_event("worker.state", w.to_dict())

                        # Route result back to the originating client
                        await self._send_result_to_client(request_id, params)

                elif method == METHOD_WORKER_HEARTBEAT:
                    pass

        except (ConnectionResetError, BrokenPipeError):
            _log.warning("Worker %s disconnected", worker_id or "unknown")
        finally:
            if worker_id:
                self._pool.unregister_worker(worker_id)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ---- client connections ----

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        _log.info("Client connected")
        self._emit_event("client.connected", {})
        wid = id(writer)
        self._client_write_locks[wid] = asyncio.Lock()

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as e:
                    await self._client_respond(
                        writer, {"error": "Invalid JSON: %s" % str(e)}
                    )
                    continue

                method = msg.get("method", "")
                params = msg.get("params", {})
                msg_id = msg.get("id")

                if method == "ping":
                    await self._client_respond(
                        writer, {"id": msg_id, "result": "pong"}
                    )

                elif method == "task.submit":
                    # Non-blocking: enqueue the task and move on.
                    # The result is sent back asynchronously when the
                    # worker reports completion.
                    self._submit_task(params, msg_id, writer)

                elif method == "task.cancel":
                    request_id = params.get("request_id", "")
                    await self._cancel_task(request_id)
                    await self._client_respond(
                        writer, {"id": msg_id, "result": "cancelled"}
                    )

                elif method == "status.get":
                    await self._client_respond(
                        writer, self._get_status(msg_id)
                    )

                elif method == "monitor.subscribe":
                    self._monitor_writers.append(writer)
                    await self._client_respond(
                        writer, {"id": msg_id, "result": "subscribed"}
                    )

                elif method == "shutdown":
                    await self._client_respond(
                        writer,
                        {"id": msg_id, "result": "shutting_down"},
                    )
                    await self.shutdown()
                    break

                else:
                    await self._client_respond(
                        writer,
                        {"id": msg_id, "error": "Unknown method: %s" % method},
                    )

        except (ConnectionResetError, BrokenPipeError):
            _log.debug("Client disconnected")
        finally:
            # Cancel all inflight tasks owned by this client
            await self._cancel_client_tasks(writer)
            if writer in self._monitor_writers:
                self._monitor_writers.remove(writer)
            self._client_write_locks.pop(wid, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _client_respond(self, writer: asyncio.StreamWriter, resp: dict):
        """Write a JSON response to a client, serialized via lock."""
        lock = self._client_write_locks.get(id(writer))
        data = (json.dumps(resp) + "\n").encode()
        if lock:
            async with lock:
                writer.write(data)
                await writer.drain()
        else:
            writer.write(data)
            await writer.drain()

    def _submit_task(self, params: dict, msg_id, writer: asyncio.StreamWriter):
        """Enqueue a task without blocking the client read loop.

        The result is routed back to the client asynchronously when the
        worker reports completion (see ``_send_result_to_client``).
        """
        request_id = params.get("request_id", "")
        resource_class = params.get("resource_class", "")

        # Remember which client is waiting for this result
        self._inflight[request_id] = (msg_id, writer)

        self._emit_event("task.dispatched", {
            "request_id": request_id,
            "name": params.get("name", ""),
        })

        # Store the full request data on the pool so the dispatch
        # callback can access it when a worker becomes available.
        asyncio.ensure_future(
            self._pool.enqueue_task(
                request_id=request_id,
                request_data=params,
                resource_class=resource_class,
            )
        )

    async def _send_result_to_client(self, request_id: str, result: dict):
        """Route a worker result back to the originating client."""
        entry = self._inflight.pop(request_id, None)
        if entry is None:
            _log.warning("No client waiting for result %s", request_id)
            return
        msg_id, writer = entry
        resp = {"id": msg_id, "result": result}
        try:
            await self._client_respond(writer, resp)
        except Exception as e:
            _log.warning("Failed to send result to client: %s", e)

    # ---- cancellation ----

    async def _cancel_task(self, request_id: str):
        """Cancel a single task by request_id."""
        w = self._pool.cancel_task(request_id)
        if w is not None:
            # Task is running on a worker -- send cancel message
            await self._send_cancel_to_worker(w, request_id)
        # Remove from inflight so we don't try to route a stale result
        self._inflight.pop(request_id, None)

    async def _cancel_client_tasks(self, writer: asyncio.StreamWriter):
        """Cancel all inflight tasks owned by a disconnecting client."""
        to_cancel = [
            rid for rid, (_, w) in list(self._inflight.items()) if w is writer
        ]
        if to_cancel:
            _log.info("Client disconnected, cancelling %d inflight task(s)", len(to_cancel))
        for rid in to_cancel:
            await self._cancel_task(rid)

    async def _send_cancel_to_worker(self, worker, request_id: str):
        """Send a task.cancel message to a worker."""
        if worker.writer is None:
            return
        try:
            msg = build_task_cancel(request_id)
            worker.writer.write(encode_message(msg))
            await worker.writer.drain()
            _log.info("Sent cancel for %s to worker %s", request_id, worker.worker_id)
        except Exception as e:
            _log.warning("Failed to send cancel to worker %s: %s", worker.worker_id, e)

    # ---- dispatch callback ----

    async def _on_dispatch(self, worker: WorkerInfo, request_data: dict):
        """Called by PoolManager when a task is assigned to a worker.

        Sends the task.execute message to the worker over its TCP connection.
        """
        if worker.writer is None:
            _log.error("Worker %s has no writer", worker.worker_id)
            return
        request_id = request_data.get("request_id", "")
        _log.info(
            "Sending task %s to worker %s",
            request_data.get("name", request_id),
            worker.worker_id,
        )
        task_msg = build_task_execute(
            request_id=request_id,
            name=request_data.get("name", ""),
            callable_spec=request_data.get("callable_spec", ""),
            shell=request_data.get("shell", "pytask"),
            body=request_data.get("body"),
            srcdir=request_data.get("srcdir", ""),
            rundir=request_data.get("rundir", ""),
            pythonpath=request_data.get("pythonpath", []),
            params=request_data.get("params", {}),
            inputs=request_data.get("inputs", []),
            env=request_data.get("env", {}),
        )
        worker.writer.write(encode_message(task_msg))
        await worker.writer.drain()
        self._emit_event("worker.state", worker.to_dict())

    # ---- worker launch / kill ----

    async def _launch_worker(self, resource_class: str = ""):
        """Launch a worker subprocess that connects back to the daemon.

        For the ``local`` runner, forks a ``dfm worker`` process directly.
        For ``lsf``, submits a ``dfm worker`` via bsub so the worker
        runs inside an LSF job slot.
        """
        # Use FQDN so remote LSF hosts can resolve the daemon host
        import socket as _socket
        addr = "%s:%d" % (_socket.getfqdn(), self._resolved_worker_port)

        if self._config.type == "lsf":
            await self._launch_worker_lsf(addr, resource_class)
        else:
            await self._launch_worker_local(addr, resource_class)

    async def _launch_worker_local(self, addr: str, resource_class: str = ""):
        """Fork a local ``dfm worker`` subprocess."""
        cmd = self._resolve_worker_cmd(addr)

        if resource_class:
            cmd.extend(["--resource-class", resource_class])

        _log.info("Launching local worker: %s", " ".join(cmd))

        # Direct worker output to a log file so it can be inspected
        log_dir = os.path.join(self._dfm_dir, "workers")
        os.makedirs(log_dir, exist_ok=True)
        import uuid as _uuid
        log_path = os.path.join(log_dir, "worker_%s.log" % _uuid.uuid4().hex[:8])
        log_fp = open(log_path, "w")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_fp,
            stderr=asyncio.subprocess.STDOUT,
        )
        log_fp.close()
        _log.info("Worker process started (pid=%d, log=%s)", proc.pid, log_path)

    async def _launch_worker_lsf(self, addr: str, resource_class: str = ""):
        """Submit a ``dfm worker`` via bsub so it runs inside an LSF job."""
        from .lsf_job import build_bsub_cmd, bsub_submit
        from .runner_backend import ResourceReq

        # Use the resource class definition when available so each worker
        # requests only the memory/cores it actually needs instead of the
        # global default (which may be far larger than necessary).
        rc = (self._config.resource_classes.get(resource_class)
              if resource_class else None)

        if rc is not None:
            resource_req = ResourceReq(
                cores=rc.cores,
                memory=rc.memory,
                queue=rc.queue or self._config.lsf.queue,
                project=self._config.lsf.project,
                resource_select=list(self._config.lsf.resource_select)
                                + list(rc.resource_select),
            )
        else:
            resource_req = ResourceReq(
                cores=self._config.defaults.cores,
                memory=self._config.defaults.memory,
                queue=self._config.lsf.queue,
                project=self._config.lsf.project,
                resource_select=list(self._config.lsf.resource_select),
            )

        # Resolve the worker command using the same Python the daemon runs
        worker_cmd = self._resolve_worker_cmd(addr)

        log_dir = os.path.join(self._dfm_dir, "workers")
        os.makedirs(log_dir, exist_ok=True)
        cmd = build_bsub_cmd(resource_req, self._config.lsf, worker_cmd, resource_class, log_dir=log_dir)
        _log.info("Launching LSF worker: %s", " ".join(cmd))

        # bsub_submit is synchronous; run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            job_id = await loop.run_in_executor(None, bsub_submit, cmd)
            _log.info("LSF job submitted: %s", job_id)
        except RuntimeError as e:
            _log.error("Failed to submit LSF worker: %s", e)
            raise

    def _resolve_worker_cmd(self, addr: str) -> list:
        """Build the worker command using this daemon's own Python path.

        Propagates the daemon's log level so worker output matches.
        """
        dfm_bin = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])))
        dfm_script = os.path.join(dfm_bin, "dfm")
        if os.path.isfile(dfm_script):
            cmd = [dfm_script]
        else:
            cmd = [sys.executable, "-m", "dv_flow.mgr"]

        # Propagate daemon log level to worker
        root_level = logging.getLogger().level
        if root_level <= logging.DEBUG:
            cmd.extend(["--log-level", "DEBUG"])
        elif root_level <= logging.INFO:
            cmd.extend(["--log-level", "INFO"])

        cmd.extend(["worker", "--connect", addr])
        return cmd

    async def _kill_worker(self, worker: WorkerInfo):
        """Shut down a worker.

        Sends a protocol shutdown message over the TCP connection,
        then bkills the LSF job if the worker is an LSF worker.
        """
        if worker.writer:
            try:
                msg = build_worker_shutdown()
                worker.writer.write(encode_message(msg))
                await worker.writer.drain()
            except Exception:
                pass

        # For LSF workers, also bkill the job to ensure cleanup
        if worker.lsf_job_id:
            from .lsf_job import bkill
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, bkill, worker.lsf_job_id)
            except Exception as e:
                _log.warning("bkill failed for worker %s (job %s): %s",
                             worker.worker_id, worker.lsf_job_id, e)

    # ---- status ----

    def _get_status(self, msg_id) -> dict:
        workers = [w.to_dict() for w in self._pool.workers.values()]
        return {
            "id": msg_id,
            "result": {
                "pid": os.getpid(),
                "workers": workers,
                "pending_tasks": self._pool.pending_count,
                "runner": self._config.type,
            },
        }

    # ---- monitor events ----

    def _emit_event(self, method: str, params: dict):
        if not self._monitor_writers:
            return
        event = json.dumps({"method": method, "params": params}) + "\n"
        data = event.encode("utf-8")
        dead = []
        for w in self._monitor_writers:
            try:
                w.write(data)
            except Exception:
                dead.append(w)
        for w in dead:
            self._monitor_writers.remove(w)

    # ---- state file ----

    def _write_state_file(self):
        state = {
            "pid": os.getpid(),
            "socket": self._socket_path,
            "worker_port": self._resolved_worker_port,
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runner": self._config.type,
        }
        with open(self._state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _remove_state_file(self):
        if os.path.exists(self._state_path):
            try:
                os.unlink(self._state_path)
            except OSError:
                pass


def is_daemon_alive(state_path: str) -> bool:
    """Check if a daemon described by state_path is alive."""
    if not os.path.isfile(state_path):
        return False
    try:
        with open(state_path) as f:
            state = json.load(f)
        pid = state.get("pid", 0)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except (json.JSONDecodeError, OSError, KeyError):
        return False
