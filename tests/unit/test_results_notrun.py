"""Selected tests that reported no Result: `notrun` (naming the blocker) or
`error` ("no result produced")."""
import json
import os
import sys

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.ext_rgy import ExtRgy


@pytest.fixture(autouse=True)
def reset_extrgy(monkeypatch):
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    monkeypatch.delenv("DFM_RESULTS_FORMATS", raising=False)
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path


TASK_PY = '''
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.results import api as R

async def Case(ctxt, input):
    r = R.mk_result(ctxt, "std.TestResult", name=input.params.label)
    R.finish(r)
    return TaskDataResult(output=[r])
'''


def _case(name, needs=""):
    return """
  - name: %s
    shell: pytask
    run: task.py::Case
    %s
    tags: [{std.Test: {name: %s}}]
    with:
      label: {type: str, value: "%s"}
""" % (name, ("needs: [%s]" % needs) if needs else "", name, name)


FLOW = """
package:
  name: nr
  tasks:
  - name: build
    shell: bash
    run: |
      echo "error: compile failed"
      exit 1
""" + _case("t1") + _case("t2", "build") + _case("t3", "build") + """
  - name: soc
    uses: std.TestSuite
    needs: [t2, t3]
  - root: tests
    uses: std.TestRunner
    needs: [t1, soc]
  - name: nocheck
    shell: bash
    tags: [{std.Test: {name: nocheck}}]
    run: echo ran
  - root: tests2
    uses: std.TestRunner
    needs: [t1, nocheck]
"""


def _run(tmp_path, *argv):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    (tmp_path / "flow.dv").write_text(FLOW)
    (tmp_path / "task.py").write_text(TASK_PY)
    args, extra = get_parser().parse_known_args(["run", "--root", str(tmp_path)] + list(argv))
    args.task_args = extra       # as __main__ does: task flags (`--tests`) go to the task
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        rc = CmdRun()(args)
    finally:
        os.chdir(old)
    with open(tmp_path / "rundir" / "out" / "latest" / "results.json") as f:
        return rc, json.load(f)


def _walk(n, path=""):
    p = (path + "/" + n["name"]) if path else n["name"]
    yield p, n
    for c in n.get("children", []):
        yield from _walk(c, p)


def test_build_failure_blocks_two_of_three(tmp_path):
    rc, d = _run(tmp_path, "tests")
    assert rc != 0
    paths = dict(_walk(d["result"]))
    assert d["result"]["type"] == "std.TestRunResult"
    assert paths["tests/t1"]["status"] == "pass"
    for t in ("t2", "t3"):
        n = paths["tests/soc/" + t]
        assert n["status"] == "notrun" and n["msg"] == "blocked: nr.build failed"
        assert n["type"] == "std.TestResult"
    assert "tests/_tasks/build" in paths
    s = d["summary"]
    assert s["counts"]["pass"] == 1 and s["counts"]["notrun"] == 2
    assert s["status"] == "error"
    fails = {f["path"]: f for f in s["failures"]}
    assert set(fails) == {"tests/soc/t2", "tests/soc/t3", "tests/_tasks/build"}


def test_test_without_a_result_is_an_error(tmp_path):
    rc, d = _run(tmp_path, "tests2")
    assert rc == 0
    paths = dict(_walk(d["result"]))
    n = paths["tests2/nocheck"]
    assert n["status"] == "error" and n["msg"] == "no result produced"
    assert paths["tests2/t1"]["status"] == "pass"
    assert d["summary"]["status"] == "error"
    assert d["summary"]["counts"]["error"] == 1 and d["summary"]["counts"]["pass"] == 1


def test_selection_only_counts_selected(tmp_path):
    rc, d = _run(tmp_path, "tests", "--tests", "t1")   # task flags follow the task
    assert rc == 0
    names = [p for p, _ in _walk(d["result"])]
    assert names == ["tests", "tests/t1"]
