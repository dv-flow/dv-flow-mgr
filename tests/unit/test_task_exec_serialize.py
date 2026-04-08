"""Tests for task serialization and deserialization."""
import dataclasses as dc
import pytest
from unittest.mock import MagicMock, PropertyMock
from pydantic import BaseModel
from dv_flow.mgr.task_exec_serialize import (
    serialize_task, deserialize_result,
    _get_callable_spec, _get_shell, _get_body, _get_tags,
)
from dv_flow.mgr.runner_backend import TaskExecRequest, ResourceReq
from dv_flow.mgr.runner_config import RunnerConfig, LsfConfig, ResourceDefaults
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE


class _MockParams(BaseModel):
    type: str = "verilogSource"
    include: list = []


class _MockTaskDef:
    def __init__(self, shell="pytask", run=None, tags=None):
        self.shell = shell
        self.run = run  # callable spec for pytask (e.g. "mod.Class")
        self.tags = tags or []


def _make_task_node(
    name="pkg.compile.gcc",
    srcdir="/proj/src",
    rundir="/proj/rundir/compile",
    params=None,
    taskdef=None,
    in_params=None,
    result=None,
    task_callable=None,
):
    """Build a mock task node with the fields serialize_task accesses."""
    node = MagicMock()
    node.name = name
    node.srcdir = srcdir
    node.rundir = rundir
    node.params = params or _MockParams()
    node.taskdef = taskdef or _MockTaskDef()
    node.in_params = in_params or []
    node.result = result
    if task_callable is not None:
        node.task = task_callable
    else:
        node.task = MagicMock()
        node.task.body = None
    return node


class TestSerializeTask:
    def test_basic_fields(self):
        node = _make_task_node()
        req = serialize_task(node, RunnerConfig())
        assert req.name == "pkg.compile.gcc"
        assert req.srcdir == "/proj/src"
        assert req.rundir == "/proj/rundir/compile"
        assert req.shell == "pytask"
        assert req.body is None

    def test_params_serialized(self):
        node = _make_task_node(params=_MockParams(type="verilogSource", include=["*.sv"]))
        req = serialize_task(node, RunnerConfig())
        assert req.params["type"] == "verilogSource"
        assert req.params["include"] == ["*.sv"]

    def test_pythonpath_includes_srcdir(self):
        node = _make_task_node(srcdir="/proj/src")
        req = serialize_task(node, RunnerConfig())
        assert "/proj/src" in req.pythonpath

    def test_shell_task_body_preserved(self):
        td = _MockTaskDef(shell="bash")
        callable_mock = MagicMock()
        callable_mock.body = "echo hello"
        node = _make_task_node(taskdef=td, task_callable=callable_mock)
        req = serialize_task(node, RunnerConfig())
        assert req.shell == "bash"
        assert req.body == "echo hello"

    def test_rundir_list_joined(self):
        node = _make_task_node(rundir=["compile", "gcc"])
        req = serialize_task(node, RunnerConfig())
        assert req.rundir == "compile/gcc"

    def test_resource_req_from_tags(self):
        td = _MockTaskDef(run="some.Callable", tags=[{"std.ResourceTag": {"cores": 4, "memory": "8G"}}])
        node = _make_task_node(taskdef=td)
        req = serialize_task(node, RunnerConfig())
        assert req.resource_req.cores == 4
        assert req.resource_req.memory == "8G"

    def test_env_passed_through(self):
        node = _make_task_node()
        req = serialize_task(node, RunnerConfig(), env={"PATH": "/usr/bin"})
        assert req.env["PATH"] == "/usr/bin"

    def test_inputs_serialized(self):
        item = MagicMock()
        item.model_dump = MagicMock(return_value={"type": "std.FileSet", "files": ["a.sv"]})
        node = _make_task_node(in_params=[item])
        req = serialize_task(node, RunnerConfig())
        assert len(req.inputs) == 1
        assert req.inputs[0]["type"] == "std.FileSet"


class TestDeserializeResult:
    def test_basic(self):
        data = {
            "status": 0,
            "changed": True,
            "output": [],
            "markers": [],
            "memento": None,
        }
        result = deserialize_result(data)
        assert result.status == 0
        assert result.changed is True
        assert result.output == []
        assert result.markers == []

    def test_markers_reconstructed(self):
        data = {
            "status": 1,
            "changed": False,
            "output": [],
            "markers": [{"msg": "compile failed", "severity": "error"}],
            "memento": None,
        }
        result = deserialize_result(data)
        assert len(result.markers) == 1
        assert result.markers[0].msg == "compile failed"
        assert result.markers[0].severity == SeverityE.Error

    def test_output_reconstruction_with_runner(self):
        mock_runner = MagicMock()
        mock_item = MagicMock()
        mock_runner.mkDataItem.return_value = mock_item

        data = {
            "status": 0,
            "changed": True,
            "output": [
                {"type": "std.FileSet", "basedir": "/proj/out", "files": ["a.sv"],
                 "src": "compile.gcc", "seq": 0}
            ],
            "markers": [],
            "memento": None,
        }
        result = deserialize_result(data, runner=mock_runner)
        assert len(result.output) == 1
        mock_runner.mkDataItem.assert_called_once()
        assert mock_item.src == "compile.gcc"
        assert mock_item.seq == 0

    def test_output_without_runner_passes_dicts(self):
        data = {
            "status": 0,
            "changed": False,
            "output": [{"type": "std.FileSet", "files": ["a.sv"]}],
            "markers": [],
        }
        result = deserialize_result(data, runner=None)
        assert len(result.output) == 1
        assert isinstance(result.output[0], dict)

    def test_memento_preserved(self):
        data = {
            "status": 0,
            "changed": False,
            "output": [],
            "markers": [],
            "memento": {"key": "value"},
        }
        result = deserialize_result(data)
        assert result.memento == {"key": "value"}


class TestGetCallableSpec:
    def test_from_taskdef_run(self):
        td = _MockTaskDef(run="dv_flow.mgr.std.fileset.FileSet")
        node = MagicMock(taskdef=td, task=None)
        spec = _get_callable_spec(node)
        assert spec == "dv_flow.mgr.std.fileset.FileSet"

    def test_no_taskdef(self):
        node = MagicMock(taskdef=None)
        node.task = MagicMock()
        node.task.body = "dv_flow.mgr.std.fileset.FileSet"
        assert _get_callable_spec(node) == "dv_flow.mgr.std.fileset.FileSet"

    def test_none_everywhere(self):
        node = MagicMock(taskdef=None, task=None)
        assert _get_callable_spec(node) == ""


class TestGetShell:
    def test_from_taskdef(self):
        node = MagicMock(taskdef=_MockTaskDef(shell="bash"))
        node.task = MagicMock()
        assert _get_shell(node) == "bash"

    def test_default_pytask(self):
        node = MagicMock(taskdef=None)
        assert _get_shell(node) == "pytask"


class TestGetBody:
    def test_with_body(self):
        node = MagicMock()
        node.task = MagicMock()
        node.task.body = "echo hello"
        assert _get_body(node) == "echo hello"

    def test_no_body(self):
        node = MagicMock()
        node.task = MagicMock()
        node.task.body = None
        assert _get_body(node) is None


class TestGetTags:
    def test_with_tags(self):
        td = _MockTaskDef(tags=["std.ResourceTag"])
        node = MagicMock(taskdef=td)
        assert _get_tags(node) == ["std.ResourceTag"]

    def test_no_taskdef(self):
        node = MagicMock(taskdef=None)
        assert _get_tags(node) == []
