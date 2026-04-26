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
import sys
import time
from typing import Any, Dict, List, Optional, Type

from .runner_config import RunnerConfig
from .worker_pool_host import WorkerPoolHost


_log = logging.getLogger("Daemon")

DAEMON_STATE_FILE = "daemon.json"
DAEMON_SOCKET_FILE = "daemon.sock"


class Daemon:
    """Background pool manager daemon.

    Delegates worker management (TCP listener, launch, dispatch) to a
    WorkerPoolHost and adds a Unix-socket client interface on top for
    ``dfm run`` auto-detect and monitoring.
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

        self._host = WorkerPoolHost(
            config=self._config,
            project_root=project_root,
            on_event=self._emit_event,
        )

        self._client_server: Optional[asyncio.AbstractServer] = None
        self._monitor_writers: List[asyncio.StreamWriter] = []
        self._running = False

        # Per-client write locks keyed by writer id, so background
        # response tasks can safely write to a client connection.
        self._client_write_locks: Dict[int, asyncio.Lock] = {}

        # Map request_id -> (msg_id, client_writer) so we can route
        # results back to the originating client asynchronously.
        self._inflight: Dict[str, tuple] = {}

    @property
    def pool(self) -> 'PoolManager':
        return self._host.pool

    @property
    def socket_path(self) -> str:
        return self._socket_path

    @property
    def state_path(self) -> str:
        return self._state_path

    @property
    def worker_port(self) -> int:
        return self._host.worker_port

    async def run(self):
        """Start daemon and run until shutdown."""
        os.makedirs(self._dfm_dir, exist_ok=True)

        await self._host.start(worker_port=self._worker_port)

        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)
        self._client_server = await asyncio.start_unix_server(
            self._handle_client, path=self._socket_path
        )
        _log.info("Client listener on %s", self._socket_path)

        self._write_state_file()
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
        await self._host.stop()

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
            self._host.pool.enqueue_task(
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
        w = self._host.pool.cancel_task(request_id)
        if w is not None:
            await self._host.send_cancel_to_worker(w, request_id)
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

    # ---- status ----

    def _get_status(self, msg_id) -> dict:
        workers = [w.to_dict() for w in self._host.pool.workers.values()]
        return {
            "id": msg_id,
            "result": {
                "pid": os.getpid(),
                "workers": workers,
                "pending_tasks": self._host.pool.pending_count,
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
            "worker_port": self._host.worker_port,
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
