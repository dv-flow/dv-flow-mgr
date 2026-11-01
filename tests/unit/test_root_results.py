"""The root-task rule at graph build, and std.check.Produces."""
import os
import sys

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.rootcheck import produces_result, root_problem


@pytest.fixture(autouse=True)
def reset_extrgy(monkeypatch):
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path


class _T:
    def __init__(self, name, uses=None):
        self.name, self.uses = name, uses


_TYPES = {}
for n, u in [("std.Result", None), ("std.TestRunResult", "std.Result"), ("std.FileSet", None)]:
    _TYPES[n] = _T(n, _TYPES.get(u))


def test_rootcheck_predicate():
    resolve = _TYPES.get
    assert produces_result([{"type": "std.TestRunResult"}], resolve)
    assert produces_result(["std.Result"], resolve)
    assert not produces_result([{"type": "std.FileSet", "filetype": "x"}], resolve)
    assert not produces_result(None, resolve)

    class Task:
        name, is_root, produces = "p.t", True, [{"type": "std.FileSet"}]
    assert "it declares std.FileSet" in root_problem(Task(), None, resolve)
    Task.is_root = False
    assert root_problem(Task(), None, resolve) is None


FLOW = """
package:
  name: rc
  tasks:
  - root: bare
    shell: bash
    run: echo hi
  - root: good
    shell: pytask
    run: task.py::Ok
    produces:
    - type: std.Result
  - root: liar
    shell: bash
    run: echo hi
    produces:
    - type: std.FileSet
    requires:
    - std.check.Produces: {type: std.Result}
"""

TASK_PY = '''
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.results import api as R

async def Ok(ctxt, input):
    r = R.mk_result(ctxt)
    R.finish(r)
    return TaskDataResult(output=[r])
'''


def _run(tmp_path, task, config=None):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    (tmp_path / "flow.dv").write_text(FLOW)
    (tmp_path / "task.py").write_text(TASK_PY)
    if config:
        (tmp_path / ".dfm").mkdir(exist_ok=True)
        (tmp_path / ".dfm" / "config.yaml").write_text(config)
    args = get_parser().parse_args(["run", "--root", str(tmp_path), task])
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        return CmdRun()(args)
    finally:
        os.chdir(old)


def test_bare_root_warns_at_graph_build(tmp_path, capsys):
    assert _run(tmp_path, "bare") == 0
    out = capsys.readouterr()
    assert "root task 'rc.bare' declares no std.Result" in out.out + out.err


def test_compliant_root_is_quiet(tmp_path, capsys):
    assert _run(tmp_path, "good") == 0
    out = capsys.readouterr()
    assert "declares no std.Result" not in out.out + out.err


def test_strict_roots_error_with_location(tmp_path, capsys):
    rc = _run(tmp_path, "bare", config="results:\n  strict_roots: true\n")
    assert rc == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "declares no std.Result" in text and "strict_roots" in text
    assert "produces:" in text            # the hint says what to write
    assert "flow.dv:5" in text.replace("\n", "")   # and where the task is (console wraps)


def test_produces_check(tmp_path, capsys):
    rc = _run(tmp_path, "liar")
    assert rc == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "does not declare what it produces" in text
    assert "std.check.Produces" in text


# -- Phase B: a compliant root's port carries only Results -------------------

PORT_FLOW = """
package:
  name: pb
  tasks:
  - root: rep
    shell: pytask
    run: port.py::Rep
    produces:
    - type: std.Result
  - root: plain
    shell: pytask
    run: port.py::Plain
  - root: consume-rep
    shell: pytask
    run: port.py::Consume
    needs: [rep]
  - root: consume-plain
    shell: pytask
    run: port.py::Consume
    needs: [plain]
"""

PORT_PY = '''
import json, os
from dv_flow.mgr import TaskDataResult, FileSet
from dv_flow.mgr.results import api as R

async def Rep(ctxt, input):
    r = R.mk_result(ctxt)
    log = os.path.join(input.rundir, "rep.log")
    open(log, "w").write("x")
    r.artifacts.append(R.artifact(ctxt, log, role="log"))
    R.finish(r)
    return TaskDataResult(output=[r, FileSet(filetype="junk", basedir=input.rundir, files=["rep.log"])])

async def Plain(ctxt, input):
    return TaskDataResult(output=[FileSet(filetype="junk", basedir=input.rundir, files=[])])

async def Consume(ctxt, input):
    seen = [getattr(i, "type", "?") + ":" + (getattr(i, "filetype", "") or "") for i in input.inputs]
    logs = [a.files[0] for a in R.artifacts(input.inputs, role="log")]
    open(os.path.join(input.rundir, "seen.json"), "w").write(json.dumps({"seen": seen, "logs": logs}))
    r = R.mk_result(ctxt)
    R.finish(r)
    return TaskDataResult(output=[r])
'''


def _port(tmp_path, task, config=None):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    import json
    (tmp_path / "flow.dv").write_text(PORT_FLOW)
    (tmp_path / "port.py").write_text(PORT_PY)
    if config:
        (tmp_path / ".dfm").mkdir(exist_ok=True)
        (tmp_path / ".dfm" / "config.yaml").write_text(config)
    args = get_parser().parse_args(["run", "--root", str(tmp_path), "--no-results", task])
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        assert CmdRun()(args) == 0
    finally:
        os.chdir(old)
    with open(tmp_path / "rundir" / ("pb." + task) / "seen.json") as f:
        return json.load(f)


def test_dependant_of_a_root_sees_only_the_result(tmp_path):
    d = _port(tmp_path, "consume-rep")
    assert d["seen"] == ["std.Result:"]
    assert d["logs"] == ["rep.log"]          # files are reached through the Result


def test_root_without_a_result_is_not_filtered(tmp_path):
    d = _port(tmp_path, "consume-plain")
    assert d["seen"] == ["std.FileSet:junk"]


def test_filter_roots_opt_out(tmp_path):
    d = _port(tmp_path, "consume-rep", config="results:\n  filter_roots: false\n")
    assert sorted(d["seen"]) == ["std.FileSet:junk", "std.Result:"]
