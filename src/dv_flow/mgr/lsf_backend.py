#****************************************************************************
#* lsf_backend.py
#*
#* LSF runner backend that manages workers directly via an embedded
#* WorkerPoolHost.  No daemon required -- dfm run --runner lsf uses
#* this backend to launch LSF workers, dispatch tasks, and collect
#* results within the lifetime of a single run.
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
import uuid
from typing import ClassVar, Dict, Optional

from .runner_backend import RunnerBackend, TaskExecRequest
from .runner_config import RunnerConfig
from .task_data import TaskDataResult
from .worker_pool_host import WorkerPoolHost


_log = logging.getLogger("LsfBackend")


class LsfBackend(RunnerBackend):
    """LSF runner backend with embedded worker pool management.

    Starts a TCP listener for workers, launches LSF workers via bsub,
    dispatches tasks through the PoolManager, and shuts down workers
    when stopped.  Operates entirely within the ``dfm run`` process --
    no daemon required.
    """

    def __init__(self, config: Optional[RunnerConfig] = None, project_root: str = ""):
        self._config = config or RunnerConfig(type="lsf")
        self._project_root = project_root
        self._host: Optional[WorkerPoolHost] = None

        # Map request_id -> Future for routing results back to callers
        self._pending: Dict[str, asyncio.Future] = {}

    @property
    def is_remote(self) -> bool:
        return True

    async def start(self) -> None:
        """Start the embedded worker pool host."""
        # Ensure config type is lsf so WorkerPoolHost launches LSF workers
        if self._config.type != "lsf":
            self._config.type = "lsf"

        self._host = WorkerPoolHost(
            config=self._config,
            project_root=self._project_root,
        )
        await self._host.start()
        _log.info("LSF backend started (worker port %d)", self._host.worker_port)

    async def stop(self) -> None:
        """Shutdown workers and close the TCP listener."""
        # Fail any pending futures so callers don't hang
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("LSF backend stopped"))
        self._pending.clear()

        if self._host is not None:
            await self._host.stop()
            self._host = None
        _log.info("LSF backend stopped")

    async def execute_task(self, request: TaskExecRequest) -> TaskDataResult:
        """Submit a task to the embedded worker pool and wait for the result."""
        if self._host is None:
            raise RuntimeError("LSF backend not started")

        request_id = uuid.uuid4().hex[:12]

        # Build the request data dict matching the daemon/worker protocol
        request_data = {
            "request_id": request_id,
            "name": request.name,
            "callable_spec": request.callable_spec,
            "shell": request.shell,
            "body": request.body,
            "srcdir": request.srcdir,
            "rundir": request.rundir,
            "pythonpath": request.pythonpath,
            "params": request.params,
            "inputs": request.inputs,
            "env": request.env,
            "resource_class": request.resource_req.queue or "",
        }

        # Enqueue in the pool -- the returned future resolves when the
        # PoolManager's complete_task() is called by the worker handler.
        pool_future = await self._host.pool.enqueue_task(
            request_id=request_id,
            request_data=request_data,
            resource_class=request_data["resource_class"],
        )

        self._pending[request_id] = pool_future

        try:
            result_data = await pool_future
        finally:
            self._pending.pop(request_id, None)

        # Deserialize the worker result
        from .task_exec_serialize import deserialize_result
        if isinstance(result_data, dict):
            return deserialize_result(result_data)
        return TaskDataResult(status=1, changed=False, output=[], markers=[])

    async def cancel_inflight(self) -> None:
        """Cancel all tasks currently in flight."""
        if self._host is None:
            return

        pending_ids = list(self._pending.keys())
        if not pending_ids:
            return

        _log.info("Cancelling %d inflight task(s)", len(pending_ids))
        workers_to_cancel = self._host.pool.cancel_all_requests(pending_ids)
        for rid, worker in workers_to_cancel:
            await self._host.send_cancel_to_worker(worker, rid)

    async def acquire_slot(self) -> None:
        """No-op: the pool manager handles slot allocation."""
        pass

    async def release_slot(self) -> None:
        """No-op: the pool manager handles slot allocation."""
        pass
