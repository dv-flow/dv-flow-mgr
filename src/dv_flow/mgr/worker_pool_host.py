#****************************************************************************
#* worker_pool_host.py
#*
#* Shared worker pool host: TCP listener, worker protocol handling,
#* worker launch (local/LSF), and task dispatch via PoolManager.
#*
#* Used by both the standalone Daemon and the embedded LsfBackend so
#* that worker management logic is not duplicated.
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
import logging
import os
import sys
from typing import Callable, Dict, List, Optional

from .pool_manager import PoolManager, WorkerInfo
from .runner_backend import ResourceReq
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


_log = logging.getLogger("WorkerPoolHost")


class WorkerPoolHost:
    """Manages a TCP listener for workers and a PoolManager.

    Handles:
    - TCP listener that accepts worker connections and speaks the
      worker protocol (register, task.result, heartbeat).
    - Worker launch (local subprocess or LSF bsub).
    - Task dispatch to workers via PoolManager callbacks.

    Callers can provide an ``on_event`` callback to receive
    worker/task lifecycle events (used by Daemon for monitor streams).
    """

    def __init__(
        self,
        config: RunnerConfig,
        project_root: str,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self._config = config
        self._project_root = project_root
        self._on_event = on_event

        self._dfm_dir = os.path.join(os.path.realpath(project_root), ".dfm")

        self._pool = PoolManager(
            config=config.pool,
            launch_worker_fn=self._launch_worker,
            kill_worker_fn=self._kill_worker,
            dispatch_fn=self._on_dispatch,
        )

        self._worker_server: Optional[asyncio.AbstractServer] = None
        self._resolved_worker_port: int = 0

    @property
    def pool(self) -> PoolManager:
        return self._pool

    @property
    def worker_port(self) -> int:
        return self._resolved_worker_port

    # ---- lifecycle ----

    async def start(self, worker_port: int = 0):
        """Start the TCP listener for workers and the idle checker."""
        self._worker_server = await asyncio.start_server(
            self._handle_worker, "0.0.0.0", worker_port,
        )
        addr = self._worker_server.sockets[0].getsockname()
        self._resolved_worker_port = addr[1]
        _log.info("Worker listener on port %d", self._resolved_worker_port)

        self._pool.start_idle_checker()

    async def stop(self):
        """Shutdown pool, close TCP listener."""
        await self._pool.shutdown()

        if self._worker_server:
            self._worker_server.close()
            await self._worker_server.wait_closed()
            self._worker_server = None

    # ---- worker connections ----

    async def _handle_worker(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
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
                    self._emit("worker.state", info.to_dict())

                elif method == METHOD_TASK_RESULT:
                    request_id = params.get("request_id", "")
                    if worker_id:
                        self._pool.complete_task(worker_id, request_id, params)
                        self._emit("task.completed", {
                            "request_id": request_id,
                            "worker_id": worker_id,
                            "status": params.get("status", 0),
                        })
                        w = self._pool.workers.get(worker_id)
                        if w:
                            self._emit("worker.state", w.to_dict())

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

    # ---- dispatch callback ----

    async def _on_dispatch(self, worker: WorkerInfo, request_data: dict):
        """Called by PoolManager when a task is assigned to a worker."""
        if worker.writer is None:
            _log.error("Worker %s has no writer", worker.worker_id)
            return
        request_id = request_data.get("request_id", "")
        _log.info("Sending task %s to worker %s",
                  request_data.get("name", request_id), worker.worker_id)
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
        self._emit("worker.state", worker.to_dict())

    # ---- worker launch / kill ----

    async def _launch_worker(self, resource_class: str = ""):
        """Launch a worker. Delegates to local or LSF based on config."""
        import socket as _socket
        addr = "%s:%d" % (_socket.getfqdn(), self._resolved_worker_port)

        if self._config.type == "lsf":
            await self._launch_worker_lsf(addr, resource_class)
        else:
            await self._launch_worker_local(addr, resource_class)

    async def _launch_worker_local(self, addr: str, resource_class: str = ""):
        cmd = self._resolve_worker_cmd(addr)
        if resource_class:
            cmd.extend(["--resource-class", resource_class])

        _log.info("Launching local worker: %s", " ".join(cmd))

        log_dir = os.path.join(self._dfm_dir, "workers")
        os.makedirs(log_dir, exist_ok=True)
        import uuid as _uuid
        log_path = os.path.join(log_dir, "worker_%s.log" % _uuid.uuid4().hex[:8])
        log_fp = open(log_path, "w")

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=log_fp, stderr=asyncio.subprocess.STDOUT,
        )
        log_fp.close()
        _log.info("Worker process started (pid=%d, log=%s)", proc.pid, log_path)

    async def _launch_worker_lsf(self, addr: str, resource_class: str = ""):
        from .lsf_job import build_bsub_cmd, bsub_submit

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

        worker_cmd = self._resolve_worker_cmd(addr)

        log_dir = os.path.join(self._dfm_dir, "workers")
        os.makedirs(log_dir, exist_ok=True)
        cmd = build_bsub_cmd(resource_req, self._config.lsf, worker_cmd,
                             resource_class, log_dir=log_dir)
        _log.info("Launching LSF worker: %s", " ".join(cmd))

        loop = asyncio.get_event_loop()
        try:
            job_id = await loop.run_in_executor(None, bsub_submit, cmd)
            _log.info("LSF job submitted: %s", job_id)
        except RuntimeError as e:
            _log.error("Failed to submit LSF worker: %s", e)
            raise

    def _resolve_worker_cmd(self, addr: str) -> list:
        """Build the worker command using this process's own Python path."""
        dfm_bin = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])))
        dfm_script = os.path.join(dfm_bin, "dfm")
        if os.path.isfile(dfm_script):
            cmd = [dfm_script]
        else:
            cmd = [sys.executable, "-m", "dv_flow.mgr"]

        root_level = logging.getLogger().level
        if root_level <= logging.DEBUG:
            cmd.extend(["--log-level", "DEBUG"])
        elif root_level <= logging.INFO:
            cmd.extend(["--log-level", "INFO"])

        cmd.extend(["worker", "--connect", addr])
        return cmd

    async def _kill_worker(self, worker: WorkerInfo):
        """Shutdown a worker, bkill if LSF."""
        if worker.writer:
            try:
                msg = build_worker_shutdown()
                worker.writer.write(encode_message(msg))
                await worker.writer.drain()
            except Exception:
                pass

        if worker.lsf_job_id:
            from .lsf_job import bkill
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, bkill, worker.lsf_job_id)
            except Exception as e:
                _log.warning("bkill failed for worker %s (job %s): %s",
                             worker.worker_id, worker.lsf_job_id, e)

    # ---- cancel helpers ----

    async def send_cancel_to_worker(self, worker: WorkerInfo, request_id: str):
        """Send a task.cancel message to a worker."""
        if worker.writer is None:
            return
        try:
            msg = build_task_cancel(request_id)
            worker.writer.write(encode_message(msg))
            await worker.writer.drain()
            _log.info("Sent cancel for %s to worker %s",
                      request_id, worker.worker_id)
        except Exception as e:
            _log.warning("Failed to send cancel to worker %s: %s",
                         worker.worker_id, e)

    # ---- events ----

    def _emit(self, method: str, params: dict):
        if self._on_event is not None:
            self._on_event(method, params)
