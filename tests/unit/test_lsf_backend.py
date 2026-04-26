"""Tests for LsfBackend: mocked daemon interaction."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dv_flow.mgr.lsf_backend import LsfBackend
from dv_flow.mgr.runner_config import RunnerConfig, LsfConfig
from dv_flow.mgr.runner_backend import TaskExecRequest


class TestLsfBackend:
    def test_is_remote(self):
        b = LsfBackend()
        assert b.is_remote is True

    def test_execute_without_start_raises(self):
        b = LsfBackend()
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(b.execute_task(TaskExecRequest()))

    def test_start_without_daemon_raises(self, tmp_path):
        """LsfBackend.start() creates an embedded worker pool (no daemon needed)."""
        async def _run():
            b = LsfBackend(project_root=str(tmp_path))
            await b.start()
            assert b._host is not None
            assert b._host.worker_port > 0
            await b.stop()
        asyncio.run(_run())

    def test_acquire_release_noop(self):
        b = LsfBackend()
        asyncio.run(b.acquire_slot())
        asyncio.run(b.release_slot())

    def test_lsf_registered_in_ext_rgy(self):
        from dv_flow.mgr.ext_rgy import ExtRgy
        rgy = ExtRgy.inst()
        assert rgy.findRunner("lsf") is not None
        assert rgy.findRunner("lsf") is LsfBackend
