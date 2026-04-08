"""Tests for RunnerBackend ABC, LocalBackend, TaskExecRequest, ResourceReq."""
import asyncio
import pytest
from dv_flow.mgr.runner_backend import RunnerBackend, TaskExecRequest, ResourceReq
from dv_flow.mgr.runner_backend_local import LocalBackend


class TestResourceReq:
    def test_defaults(self):
        r = ResourceReq()
        assert r.cores == 1
        assert r.memory == "1G"
        assert r.queue == ""
        assert r.walltime_minutes == 60
        assert r.project == ""
        assert r.resource_select == []
        assert r.extra == {}

    def test_custom_values(self):
        r = ResourceReq(cores=4, memory="8G", queue="regr_high", project="test")
        assert r.cores == 4
        assert r.memory == "8G"
        assert r.queue == "regr_high"
        assert r.project == "test"


class TestTaskExecRequest:
    def test_defaults(self):
        req = TaskExecRequest()
        assert req.name == ""
        assert req.shell == "pytask"
        assert req.body is None
        assert req.pythonpath == []
        assert req.params == {}
        assert req.inputs == []
        assert req.env == {}
        assert req.memento is None
        assert isinstance(req.resource_req, ResourceReq)

    def test_construction_and_field_access(self):
        req = TaskExecRequest(
            name="pkg.compile.gcc",
            callable_spec="dv_flow.mgr.std.fileset.FileSet",
            shell="bash",
            body="echo hello",
            srcdir="/proj/src",
            rundir="/proj/rundir/compile",
            pythonpath=["/proj/src"],
            params={"type": "verilogSource"},
            inputs=[{"type": "std.FileSet"}],
            env={"PATH": "/usr/bin"},
            resource_req=ResourceReq(cores=2, memory="4G"),
        )
        assert req.name == "pkg.compile.gcc"
        assert req.callable_spec == "dv_flow.mgr.std.fileset.FileSet"
        assert req.shell == "bash"
        assert req.body == "echo hello"
        assert req.resource_req.cores == 2
        assert req.resource_req.memory == "4G"


class TestLocalBackend:
    def test_is_not_remote(self):
        backend = LocalBackend()
        assert backend.is_remote is False

    def test_start_stop_are_noop(self):
        backend = LocalBackend()
        asyncio.run(backend.start())
        asyncio.run(backend.stop())

    def test_execute_task_raises(self):
        backend = LocalBackend()
        with pytest.raises(NotImplementedError):
            asyncio.run(backend.execute_task(TaskExecRequest()))

    def test_acquire_release_without_jobserver(self):
        """No jobserver -> acquire/release are no-ops."""
        backend = LocalBackend(jobserver=None)
        asyncio.run(backend.acquire_slot())
        asyncio.run(backend.release_slot())


class TestRunnerBackendABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            RunnerBackend()

    def test_is_remote_default(self):
        """Concrete subclass inherits is_remote=False."""
        backend = LocalBackend()
        assert backend.is_remote is False
