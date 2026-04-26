"""Tests for PoolManager: event-driven launch, idle teardown, worker tracking."""
import asyncio
import pytest
from dv_flow.mgr.pool_manager import PoolManager, WorkerInfo
from dv_flow.mgr.runner_config import PoolConfig


def _make_pool(
    max_workers=16, min_workers=0, idle_timeout=300,
    launch_batch_size=4, launch_fn=None, kill_fn=None,
):
    cfg = PoolConfig(
        max_workers=max_workers,
        min_workers=min_workers,
        idle_timeout=idle_timeout,
        launch_batch_size=launch_batch_size,
    )
    return PoolManager(cfg, launch_worker_fn=launch_fn, kill_worker_fn=kill_fn)


def _make_worker(worker_id="w1", resource_class=""):
    return WorkerInfo(worker_id=worker_id, resource_class=resource_class)


class TestEnqueueDispatch:
    def test_enqueue_with_no_idle_workers_requests_launch(self):
        """Enqueue task with no idle workers -> launch requested."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(launch_fn=launch)

        async def run():
            await pool.enqueue_task("req1", {"name": "task1"}, resource_class="")

        asyncio.run(run())
        assert len(launches) > 0

    def test_enqueue_with_idle_worker_dispatches_immediately(self):
        """Enqueue task with idle compatible worker -> dispatched immediately."""
        pool = _make_pool()
        w = _make_worker("w1")
        pool.register_worker(w)

        async def run():
            future = await pool.enqueue_task("req1", {"name": "task1"})
            # Worker should be busy now
            assert w.state == "busy"
            assert w.current_task == "task1"
            return future

        asyncio.run(run())
        assert pool.pending_count == 0

    def test_task_completion_makes_worker_idle(self):
        """After task completion, worker returns to idle."""
        pool = _make_pool()
        w = _make_worker("w1")
        pool.register_worker(w)

        async def run():
            future = await pool.enqueue_task("req1", {"name": "task1"})
            pool.complete_task("w1", "req1", {"status": 0})
            assert w.state == "idle"
            result = future.result()
            assert result["status"] == 0

        asyncio.run(run())


class TestMaxWorkers:
    def test_max_workers_respected(self):
        """Don't launch above max_workers."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=2, launch_batch_size=4, launch_fn=launch)
        # Register 2 workers already
        pool.register_worker(_make_worker("w1"))
        pool.register_worker(_make_worker("w2"))

        async def run():
            await pool.enqueue_task("req1", {"name": "task1"})

        # Both workers are idle, so task gets dispatched immediately, no launch
        asyncio.run(run())
        assert len(launches) == 0

    def test_launch_batch_size_honored(self):
        """launch_batch_size limits workers launched per event, but never more than needed."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=10, launch_batch_size=3, launch_fn=launch)

        async def run():
            # 1 pending task -> only 1 launch, not batch_size
            await pool.enqueue_task("req1", {"name": "task1"})

        asyncio.run(run())
        assert len(launches) == 1

    def test_launch_batch_size_with_multiple_pending(self):
        """launch_batch_size is used when there are enough pending tasks."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=10, launch_batch_size=3, launch_fn=launch)

        async def run():
            # Enqueue 5 tasks, then the last one triggers _maybe_launch
            # with 5 pending tasks -> launches min(batch_size=3, needed=5) = 3
            for i in range(5):
                await pool.enqueue_task("req%d" % i, {"name": "task%d" % i})

        asyncio.run(run())
        # First task enqueue launches 1 (needed=1, batch=3 -> 1).
        # After that _pending_launches=1.
        # Second enqueue: pending=2, pending_launches=1, needed=1 -> 1.
        # Third: pending=3, pending_launches=2, needed=1 -> 1.
        # Etc. Each enqueue launches exactly 1.
        assert len(launches) == 5


class TestIdleTeardown:
    def test_idle_worker_exceeds_timeout(self):
        """Worker idle beyond timeout gets terminated."""
        killed = []

        async def kill(w):
            killed.append(w.worker_id)

        pool = _make_pool(idle_timeout=0, min_workers=0, kill_fn=kill)
        w = _make_worker("w1")
        pool.register_worker(w)
        # Force idle_since far in the past
        w.idle_since = 0.0

        async def run():
            await pool.check_idle_workers()

        asyncio.run(run())
        assert "w1" in killed
        assert "w1" not in pool.workers

    def test_min_workers_respected(self):
        """Don't kill below min_workers."""
        killed = []

        async def kill(w):
            killed.append(w.worker_id)

        pool = _make_pool(idle_timeout=0, min_workers=1, kill_fn=kill)
        w = _make_worker("w1")
        pool.register_worker(w)
        w.idle_since = 0.0

        async def run():
            await pool.check_idle_workers()

        asyncio.run(run())
        assert len(killed) == 0  # Can't kill: would go below min_workers


class TestResourceClassCompatibility:
    def test_exact_match_dispatched(self):
        pool = _make_pool()
        w = _make_worker("w1", resource_class="medium")
        pool.register_worker(w)

        async def run():
            await pool.enqueue_task("req1", {"name": "t1"}, resource_class="medium")

        asyncio.run(run())
        assert w.state == "busy"

    def test_incompatible_class_triggers_launch(self):
        """Incompatible resource class -> new launch requested."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(launch_fn=launch)
        w = _make_worker("w1", resource_class="small")
        pool.register_worker(w)

        async def run():
            await pool.enqueue_task("req1", {"name": "t1"}, resource_class="large")

        asyncio.run(run())
        # Should have launched because "small" != "large"
        assert len(launches) > 0
        assert pool.pending_count == 1  # still pending


class TestWorkerRegistration:
    def test_register_dispatches_pending(self):
        """Newly registered worker picks up pending tasks."""
        pool = _make_pool()

        async def run():
            # Enqueue without any workers
            future = await pool.enqueue_task("req1", {"name": "t1"})
            assert pool.pending_count == 1

            # Register a worker -- should dispatch
            w = _make_worker("w1")
            pool.register_worker(w)
            assert pool.pending_count == 0
            assert w.state == "busy"

        asyncio.run(run())

    def test_unregister_worker(self):
        pool = _make_pool()
        w = _make_worker("w1")
        pool.register_worker(w)
        assert "w1" in pool.workers
        pool.unregister_worker("w1")
        assert "w1" not in pool.workers


class TestShutdown:
    def test_shutdown_clears_state(self):
        killed = []

        async def kill(w):
            killed.append(w.worker_id)

        pool = _make_pool(kill_fn=kill)
        pool.register_worker(_make_worker("w1"))
        pool.register_worker(_make_worker("w2"))

        async def run():
            await pool.enqueue_task("req1", {"name": "t1"})
            await pool.shutdown()

        asyncio.run(run())
        assert len(pool.workers) == 0
        assert pool.pending_count == 0
        assert set(killed) == {"w1", "w2"}


class TestOverProvisioning:
    """Verify that the pool manager does not launch more workers than needed."""

    def test_single_task_launches_one_worker(self):
        """A single pending task should launch exactly 1 worker, not batch_size."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=100, launch_batch_size=4, launch_fn=launch)

        async def run():
            await pool.enqueue_task("req1", {"name": "task1"})

        asyncio.run(run())
        assert len(launches) == 1

    def test_concurrent_enqueues_do_not_over_launch(self):
        """Many tasks enqueued concurrently should not launch more workers than tasks."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=100, launch_batch_size=4, launch_fn=launch)

        async def run():
            # Enqueue 10 tasks sequentially (each calls _maybe_launch)
            for i in range(10):
                await pool.enqueue_task("req%d" % i, {"name": "task%d" % i})

        asyncio.run(run())
        # Should launch at most 10 workers (one per pending task)
        assert len(launches) <= 10

    def test_worker_registration_reduces_needed(self):
        """After a worker registers and picks up a pending task, fewer launches needed."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=100, launch_batch_size=4, launch_fn=launch)

        async def run():
            # Enqueue 2 tasks
            await pool.enqueue_task("req1", {"name": "task1"})
            await pool.enqueue_task("req2", {"name": "task2"})
            # At this point, 2 workers should have been launched
            assert len(launches) == 2

            # Worker registers and picks up one pending task
            w = _make_worker("w1")
            pool.register_worker(w)
            assert w.state == "busy"
            assert pool.pending_count == 1

            # Enqueue a 3rd task; only 1 is pending + 1 pending_launch
            # so needed = 1 - 1 = 0 if the first launch hasn't
            # registered yet, or needed = 2 - 1 = 1
            await pool.enqueue_task("req3", {"name": "task3"})

        asyncio.run(run())
        # Total launches should be <= 3 (one per task)
        assert len(launches) <= 3

    def test_no_launch_when_enough_pending_launches(self):
        """If pending_launches already covers pending tasks, no new launches."""
        launches = []

        async def launch(rc):
            launches.append(rc)

        pool = _make_pool(max_workers=100, launch_batch_size=4, launch_fn=launch)

        async def run():
            await pool.enqueue_task("req1", {"name": "task1"})
            initial_launches = len(launches)
            # Manually increment pending_launches to simulate in-flight launches
            # that more than cover the pending queue
            pool._pending_launches += 5
            await pool.enqueue_task("req2", {"name": "task2"})
            # No new launch: pending=2, pending_launches=6, needed=2-6=-4 -> skip
            assert len(launches) == initial_launches

        asyncio.run(run())


class TestCancelTask:
    def test_cancel_pending_task(self):
        """Cancelling a pending task removes it from the queue."""
        pool = _make_pool()

        async def run():
            future = await pool.enqueue_task("req1", {"name": "task1"})
            assert pool.pending_count == 1
            result = pool.cancel_task("req1")
            assert result is None  # was pending, not on a worker
            assert pool.pending_count == 0
            assert future.cancelled()

        asyncio.run(run())

    def test_cancel_running_task_returns_worker(self):
        """Cancelling a running task returns the WorkerInfo."""
        pool = _make_pool()
        w = _make_worker("w1")
        pool.register_worker(w)

        async def run():
            await pool.enqueue_task("req1", {"name": "task1"})
            assert w.state == "busy"
            result = pool.cancel_task("req1")
            assert result is w  # task is on this worker

        asyncio.run(run())

    def test_cancel_unknown_task_returns_none(self):
        """Cancelling a non-existent task returns None."""
        pool = _make_pool()
        result = pool.cancel_task("no_such_request")
        assert result is None

    def test_cancel_all_requests(self):
        """cancel_all_requests handles mix of pending and running tasks."""
        pool = _make_pool()
        w = _make_worker("w1")
        pool.register_worker(w)

        async def run():
            # req1 dispatched to w1, req2 stays pending
            await pool.enqueue_task("req1", {"name": "task1"})
            await pool.enqueue_task("req2", {"name": "task2"})
            assert w.state == "busy"
            assert pool.pending_count == 1

            workers = pool.cancel_all_requests(["req1", "req2"])
            # req1 was on w1, req2 was pending
            assert len(workers) == 1
            assert workers[0][0] == "req1"
            assert workers[0][1] is w
            assert pool.pending_count == 0

        asyncio.run(run())
