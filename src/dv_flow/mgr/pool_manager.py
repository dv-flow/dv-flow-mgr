#****************************************************************************
#* pool_manager.py
#*
#* Event-driven worker pool manager. Backend-agnostic: delegates
#* actual worker launch/kill to a RunnerBackend.
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
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .runner_config import PoolConfig


_log = logging.getLogger("PoolManager")


class WorkerInfo:
    """Tracks state of a single worker."""

    __slots__ = (
        "worker_id", "resource_class", "hostname", "pid",
        "lsf_job_id", "state", "current_task", "idle_since",
        "writer", "_pending_future", "_pending_request_id",
    )

    def __init__(
        self,
        worker_id: str,
        resource_class: str = "",
        hostname: str = "",
        pid: int = 0,
        lsf_job_id: str = "",
    ):
        self.worker_id = worker_id
        self.resource_class = resource_class
        self.hostname = hostname
        self.pid = pid
        self.lsf_job_id = lsf_job_id
        self.state = "idle"           # idle | busy | pending
        self.current_task: Optional[str] = None
        self.idle_since: float = time.monotonic()
        self.writer: Optional[asyncio.StreamWriter] = None
        self._pending_future: Optional[asyncio.Future] = None
        self._pending_request_id: Optional[str] = None

    def mark_busy(self, task_name: str):
        self.state = "busy"
        self.current_task = task_name
        self.idle_since = 0.0

    def mark_idle(self):
        self.state = "idle"
        self.current_task = None
        self.idle_since = time.monotonic()

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "resource_class": self.resource_class,
            "hostname": self.hostname,
            "state": self.state,
            "current_task": self.current_task,
            "lsf_job_id": self.lsf_job_id,
        }


class _PendingTask:
    """A task waiting for a worker."""
    __slots__ = ("request_id", "request_data", "resource_class", "future")

    def __init__(self, request_id: str, request_data: dict, resource_class: str):
        self.request_id = request_id
        self.request_data = request_data
        self.resource_class = resource_class
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


class PoolManager:
    """Event-driven worker pool manager.

    Manages a pool of workers, dispatching tasks to idle workers and
    scaling the pool up/down based on demand.

    The pool manager is backend-agnostic: the ``launch_worker_fn`` and
    ``kill_worker_fn`` callbacks handle the actual mechanics of starting
    and stopping workers (bsub, sbatch, fork, etc.).
    """

    def __init__(
        self,
        config: PoolConfig,
        launch_worker_fn: Optional[Callable] = None,
        kill_worker_fn: Optional[Callable] = None,
        dispatch_fn: Optional[Callable] = None,
    ):
        self._config = config
        self._launch_worker_fn = launch_worker_fn
        self._kill_worker_fn = kill_worker_fn
        self._dispatch_fn = dispatch_fn

        # Worker registry: worker_id -> WorkerInfo
        self._workers: Dict[str, WorkerInfo] = {}

        # Pending task queue
        self._pending: List[_PendingTask] = []

        # Counts of workers launched but not yet registered
        self._pending_launches: int = 0

        # Idle teardown task handle
        self._idle_task: Optional[asyncio.Task] = None

    @property
    def workers(self) -> Dict[str, WorkerInfo]:
        return self._workers

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def active_worker_count(self) -> int:
        """Number of registered + pending-launch workers."""
        return len(self._workers) + self._pending_launches

    def idle_workers(self, resource_class: str = "") -> List[WorkerInfo]:
        """Return idle workers compatible with the given resource class."""
        result = []
        for w in self._workers.values():
            if w.state != "idle":
                continue
            if resource_class and w.resource_class != resource_class:
                # A larger class can serve a smaller one (compatibility)
                # For now, exact match only
                continue
            result.append(w)
        return result

    def register_worker(self, info: WorkerInfo):
        """Register a newly-connected worker."""
        self._workers[info.worker_id] = info
        if self._pending_launches > 0:
            self._pending_launches -= 1
        _log.info("Worker registered: %s (class=%s, host=%s)",
                  info.worker_id, info.resource_class, info.hostname)

        # Try to dispatch pending tasks to this worker
        self._try_dispatch()

    def unregister_worker(self, worker_id: str):
        """Remove a worker (disconnected or killed)."""
        w = self._workers.pop(worker_id, None)
        if w:
            _log.info("Worker unregistered: %s", worker_id)
            # If worker was busy, the task should be re-queued by the caller

    async def enqueue_task(
        self,
        request_id: str,
        request_data: dict,
        resource_class: str = "",
    ) -> asyncio.Future:
        """Enqueue a task for execution.

        Returns a Future that resolves to the task result dict.
        """
        pt = _PendingTask(request_id, request_data, resource_class)

        # Try immediate dispatch to an idle worker
        idle = self.idle_workers(resource_class)
        if idle:
            worker = idle[0]
            self._dispatch_to_worker(worker, pt)
            return pt.future

        # No idle worker available -- queue and possibly launch
        self._pending.append(pt)
        await self._maybe_launch(resource_class)
        return pt.future

    async def _maybe_launch(self, resource_class: str = ""):
        """Launch workers if below max_workers and there are unserved pending tasks.

        Caps the number of launches at the number of pending tasks that
        don't already have a worker being launched for them, preventing
        over-provisioning when many tasks are enqueued concurrently.
        Rechecks capacity before each launch since other coroutines may
        have launched workers while we were yielding.
        """
        if self._launch_worker_fn is None:
            return
        active = self.active_worker_count
        if active >= self._config.max_workers:
            _log.debug("At max_workers (%d), not launching", self._config.max_workers)
            return

        # Only launch as many workers as there are unserved pending tasks
        needed = len(self._pending) - self._pending_launches
        if needed <= 0:
            return

        n = min(
            self._config.launch_batch_size,
            self._config.max_workers - active,
            needed,
        )
        _log.info("Launching %d worker(s) (active=%d, max=%d, pending=%d, needed=%d)",
                  n, active, self._config.max_workers, len(self._pending), needed)
        for _ in range(n):
            # Recheck capacity before each launch since concurrent
            # coroutines may have launched workers while we yielded.
            if self.active_worker_count >= self._config.max_workers:
                break
            if len(self._pending) - self._pending_launches <= 0:
                break
            self._pending_launches += 1
            try:
                await self._launch_worker_fn(resource_class)
            except Exception as e:
                self._pending_launches -= 1
                _log.error("Failed to launch worker: %s", e)

    def _try_dispatch(self):
        """Try to dispatch pending tasks to idle workers."""
        dispatched = []
        for i, pt in enumerate(self._pending):
            idle = self.idle_workers(pt.resource_class)
            if idle:
                self._dispatch_to_worker(idle[0], pt)
                dispatched.append(i)
        # Remove dispatched (reverse order to preserve indices)
        for i in reversed(dispatched):
            self._pending.pop(i)

    def _dispatch_to_worker(self, worker: WorkerInfo, pt: _PendingTask):
        """Send a task to a specific worker."""
        worker.mark_busy(pt.request_data.get("name", pt.request_id))
        worker._pending_future = pt.future
        worker._pending_request_id = pt.request_id
        _log.debug("Dispatched %s to worker %s",
                   pt.request_id, worker.worker_id)
        # Actually send the task to the worker via the daemon callback
        if self._dispatch_fn is not None:
            asyncio.ensure_future(self._dispatch_fn(worker, pt.request_data))

    def complete_task(self, worker_id: str, request_id: str, result: dict):
        """Called when a worker reports a task result."""
        w = self._workers.get(worker_id)
        if w is None:
            _log.warning("Result from unknown worker %s", worker_id)
            return
        future = getattr(w, "_pending_future", None)
        if future and not future.done():
            future.set_result(result)
        w.mark_idle()
        # Try to dispatch more pending tasks
        self._try_dispatch()

    def cancel_task(self, request_id: str) -> Optional['WorkerInfo']:
        """Cancel a task by request_id.

        If the task is still in the pending queue, removes it and cancels
        its future.  If it is dispatched to a worker, returns the
        WorkerInfo so the caller can send a cancel message to the worker.
        Returns None if the request_id is not found.
        """
        # Check pending queue first
        for i, pt in enumerate(self._pending):
            if pt.request_id == request_id:
                self._pending.pop(i)
                if not pt.future.done():
                    pt.future.cancel()
                _log.info("Cancelled pending task %s", request_id)
                return None

        # Check busy workers
        for w in self._workers.values():
            if w.state == "busy" and w._pending_request_id == request_id:
                _log.info("Task %s running on worker %s, needs cancel",
                          request_id, w.worker_id)
                return w

        _log.debug("Cancel request for unknown task %s", request_id)
        return None

    def cancel_all_requests(self, request_ids: list) -> list:
        """Cancel multiple tasks. Returns list of WorkerInfo for tasks
        currently running on workers (caller must send cancel to them)."""
        workers_to_cancel = []
        for rid in request_ids:
            w = self.cancel_task(rid)
            if w is not None:
                workers_to_cancel.append((rid, w))
        return workers_to_cancel

    async def check_idle_workers(self):
        """Terminate workers that have been idle too long.

        Called periodically (every 5 seconds) by the daemon.
        """
        now = time.monotonic()
        to_kill = []
        for w in list(self._workers.values()):
            if w.state != "idle":
                continue
            idle_secs = now - w.idle_since
            if idle_secs > self._config.idle_timeout:
                # Don't kill below min_workers
                total = len(self._workers) - len(to_kill)
                if total <= self._config.min_workers:
                    break
                to_kill.append(w)

        for w in to_kill:
            _log.info("Terminating idle worker %s (idle %.0fs > %ds)",
                      w.worker_id, now - w.idle_since, self._config.idle_timeout)
            self.unregister_worker(w.worker_id)
            if self._kill_worker_fn:
                try:
                    await self._kill_worker_fn(w)
                except Exception as e:
                    _log.error("Failed to kill worker %s: %s", w.worker_id, e)

    def start_idle_checker(self, interval: float = 5.0):
        """Start the periodic idle-worker checker."""
        async def _loop():
            try:
                while True:
                    await asyncio.sleep(interval)
                    await self.check_idle_workers()
            except asyncio.CancelledError:
                pass
        self._idle_task = asyncio.create_task(_loop())

    def stop_idle_checker(self):
        """Stop the periodic idle-worker checker."""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

    async def shutdown(self):
        """Shutdown: kill all workers and cancel pending tasks."""
        self.stop_idle_checker()
        # Cancel pending tasks
        for pt in self._pending:
            if not pt.future.done():
                pt.future.cancel()
        self._pending.clear()
        # Kill all workers
        for w in list(self._workers.values()):
            if self._kill_worker_fn:
                try:
                    await self._kill_worker_fn(w)
                except Exception as e:
                    _log.error("Error killing worker %s: %s", w.worker_id, e)
        self._workers.clear()
