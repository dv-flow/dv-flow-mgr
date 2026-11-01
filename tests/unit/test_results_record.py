"""The end-of-run recorder: rundir/out/<run-id>/results.json."""
import asyncio
import json
import logging
import os
import sys

import pytest

from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.model import ResultsFile
from dv_flow.mgr.results.recorder import ResultsRecorder
from dv_flow.mgr.util import loadProjPkgDef


@pytest.fixture(autouse=True)
def reset_extrgy():
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    os.environ.pop('MAKEFLAGS', None)
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path


TASK_PY = '''
from dv_flow.mgr import TaskDataResult, TaskMarker, SeverityE
from dv_flow.mgr.results import api as R

async def FailingCheck(ctxt, input):
    res = R.mk_result(ctxt, "std.TestResult", name="case1", testname="t1",
                      metrics={"uvm_errors": R.metric(2)})
    res.checks.append(R.eval_check(res.metrics, "uvm_errors", "uvm_errors", "==", 0))
    R.finish(res)
    return TaskDataResult(output=[res])

async def GatedFail(ctxt, input):
    # A report task that fails its status as a CI gate, with the Result
    res = R.mk_result(ctxt, "std.SuiteResult", name="suite", status="fail")
    R.finish(res)
    return TaskDataResult(output=[res], status=1,
                          markers=[TaskMarker(msg="1 test failed", severity=SeverityE.Error)])

async def Passing(ctxt, input):
    res = R.mk_result(ctxt, "std.Result", name=input.params.label or "ok")
    R.finish(res)
    return TaskDataResult(output=[res])

async def NamesCompound(ctxt, input):
    res = R.mk_result(ctxt, "std.Result", name="c", task=input.params.owner,
                      status="fail", msg="sub failed")
    return TaskDataResult(output=[res])

async def Bogus(ctxt, input):
    res = R.mk_result(ctxt, "std.Result", name="weird", status="bogus")
    return TaskDataResult(output=[res])
'''


def _write(tmp, flow):
    tmp = str(tmp)
    with open(os.path.join(tmp, "flow.dv"), "w") as f:
        f.write(flow)
    with open(os.path.join(tmp, "task.py"), "w") as f:
        f.write(TASK_PY)
    return tmp


def _run(tmp, flow, *tasks):
    tmp = _write(tmp, flow)
    rundir = os.path.join(tmp, "rundir")
    loader, pkg = loadProjPkgDef(tmp)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir, builder=builder, nproc=2)
    nodes = [builder.mkTaskNode(t) for t in tasks]
    rec = ResultsRecorder(runner, nodes, rundir, builder.run_id)
    runner.add_event_listener(rec.event)
    asyncio.run(runner.run(nodes if len(nodes) > 1 else nodes[0]))
    rf = rec.record()
    return rundir, runner, rec, rf


def _cli(tmp, flow, *argv):
    from dv_flow.mgr.__main__ import get_parser
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    tmp = _write(tmp, flow)
    args = get_parser().parse_args(["run", "--root", tmp] + list(argv))
    old = os.getcwd()
    os.chdir(tmp)
    try:
        status = CmdRun()(args)
    finally:
        os.chdir(old)
    return tmp, status


def _load(rundir, rid="latest"):
    with open(os.path.join(rundir, "out", rid, "results.json")) as f:
        return json.load(f)


def _walk(n, path=""):
    p = (path + "/" + n["name"]) if path else n["name"]
    yield p, n
    for c in n.get("children", []):
        yield from _walk(c, p)


FLOW = """
package:
  name: rr
  tasks:
  - name: case
    shell: pytask
    run: task.py::FailingCheck
  - name: gate
    shell: pytask
    run: task.py::GatedFail
  - name: hello
    shell: bash
    run: echo hello
  - name: build
    shell: bash
    run: |
      echo "compiling"
      exit 1
  - name: test
    needs: [build]
    shell: pytask
    run: task.py::Passing
    with:
      label: {type: str, value: "t"}
  - name: a
    shell: pytask
    run: task.py::Passing
    with:
      label: {type: str, value: "a"}
  - name: b
    shell: pytask
    run: task.py::Passing
    with:
      label: {type: str, value: "b"}
  - name: weird
    shell: pytask
    run: task.py::Bogus
  - name: c
    body:
    - name: sub
      shell: bash
      run: exit 1
    - name: rep
      shell: pytask
      run: task.py::NamesCompound
      with:
        owner: {type: str, value: "rr.c"}
"""


def test_result_root(tmp_path):
    rundir, runner, rec, rf = _run(tmp_path, FLOW, "rr.case")
    assert runner.status == 0                      # failure is data
    d = _load(rundir)
    ResultsFile.model_validate(d)
    import jsonschema
    from dv_flow.mgr.results.model import results_json_schema
    jsonschema.validate(d, results_json_schema())
    assert d["schema"] == "dvflow-results/1"
    assert d["result"]["type"] == "std.TestResult"
    assert d["result"]["types"] == ["std.TestResult", "std.Result"]
    assert d["result"]["status"] == "fail"
    assert d["result"]["testname"] == "t1"
    s = d["summary"]
    assert s["status"] == "fail"
    assert s["counts"]["total"] == 1 and s["counts"]["fail"] == 1
    assert len(s["failures"]) == 1
    assert s["failures"][0]["checks"][0]["name"] == "uvm_errors"
    assert os.readlink(os.path.join(rundir, "out", "latest")) == rec.run_id
    assert os.path.isfile(os.path.join(rundir, "out", rec.run_id, "summary.md"))
    assert d["run"]["exit_status"] == 0


def test_non_result_root(tmp_path):
    rundir, runner, rec, rf = _run(tmp_path, FLOW, "rr.hello")
    d = _load(rundir)
    r = d["result"]
    assert r["type"] == "std.TaskResult" and r["status"] == "pass"
    assert r["task"] == "rr.hello"
    logs = [a for a in r.get("artifacts", []) if a["role"] == "log"]
    assert logs and os.path.isfile(logs[0]["stamps"][0]["path"])
    assert d["summary"]["status"] == "pass"
    assert d["summary"]["failures"] == []


def test_build_failure(tmp_path):
    rundir, runner, rec, rf = _run(tmp_path, FLOW, "rr.test")
    assert runner.status != 0
    d = _load(rundir)
    paths = dict(_walk(d["result"]))
    assert "test/_tasks/build" in paths
    import jsonschema
    from dv_flow.mgr.results.model import results_json_schema
    jsonschema.validate(d, results_json_schema())
    b = paths["test/_tasks/build"]
    assert b["type"] == "std.TaskResult" and b["status"] == "error"
    assert b["diagnostics"] and b["diagnostics"][0]["severity"] == "error"
    assert any(a["role"] == "log" for a in b["artifacts"])
    assert paths["test"]["msg"] == "blocked: rr.build failed"
    s = d["summary"]
    assert s["status"] == "error"
    fpaths = {f["path"]: f for f in s["failures"]}
    assert "test/_tasks/build" in fpaths
    assert fpaths["test/_tasks/build"]["log"]["path"].endswith(".log")
    assert fpaths["test"]["status"] == "notrun"
    assert s["counts"]["notrun"] == 1 and s["counts"]["error"] == 1


def test_accounted_failure(tmp_path):
    # status 0 with a failing Result: nothing extra
    rundir, _, _, _ = _run(tmp_path, FLOW, "rr.case")
    assert "_tasks" not in dict(_walk(_load(rundir)["result"]))


def test_gated_failure_is_accounted(tmp_path):
    # nonzero status *and* a Result from the same task: the Result accounts for it
    rundir, runner, _, _ = _run(tmp_path, FLOW, "rr.gate")
    assert runner.status != 0
    d = _load(rundir)
    assert not any(p.endswith("_tasks") for p in dict(_walk(d["result"])))
    assert d["summary"]["status"] == "fail"


def test_compound_attribution(tmp_path):
    rundir, runner, _, _ = _run(tmp_path, FLOW, "rr.c")
    assert runner.status != 0
    d = _load(rundir)
    paths = dict(_walk(d["result"]))
    assert not any("_tasks" in p for p in paths), paths.keys()
    assert d["result"]["task"] == "rr.c"


def test_multiple_roots(tmp_path):
    rundir, _, _, rf = _run(tmp_path, FLOW, "rr.a", "rr.b")
    d = _load(rundir)
    assert d["result"]["name"] == "run"
    assert [c["name"] for c in d["result"]["children"]] == ["a", "b"]
    assert d["run"]["root"] == ["rr.a", "rr.b"]
    assert d["summary"]["counts"]["total"] == 2


def test_malformed_result(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        rundir, runner, _, _ = _run(tmp_path, FLOW, "rr.weird")
    assert runner.status == 0
    d = _load(rundir)
    assert d["result"]["status"] == "error"
    assert "bogus" in d["result"]["msg"]
    assert any("bogus" in r.getMessage() for r in caplog.records)


def test_writer_failure_does_not_fail_the_run(tmp_path, monkeypatch, capsys):
    def boom(self, rf):
        raise RuntimeError("disk full")
    monkeypatch.setattr(ResultsRecorder, "write", boom)
    tmp, status = _cli(tmp_path, FLOW, "rr.hello")
    assert status == 0
    assert "could not write run results" in capsys.readouterr().err


def test_cli_writes_record_and_prints_path(tmp_path, capsys):
    tmp, status = _cli(tmp_path, FLOW, "rr.case")
    assert status == 0
    out = capsys.readouterr().out
    assert "Results: " in out and "results.json" in out
    d = _load(os.path.join(tmp, "rundir"))
    assert d["run"]["argv"][0] == "dfm"


def test_no_results(tmp_path):
    tmp, status = _cli(tmp_path, FLOW, "--no-results", "rr.hello")
    assert status == 0
    out = os.path.join(tmp, "rundir", "out")
    found = [f for r, _, fs in os.walk(out) for f in fs if f == "results.json"]
    assert found == []


def test_up_to_date_is_reused(tmp_path):
    tmp, status = _cli(tmp_path, FLOW, "rr.hello")
    assert status == 0
    first = _load(os.path.join(tmp, "rundir"))
    assert not first["result"].get("reused", False)
    from dv_flow.mgr.__main__ import get_parser
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    ExtRgy._inst = None
    args = get_parser().parse_args(["run", "--root", tmp, "rr.hello"])
    old = os.getcwd()
    os.chdir(tmp)
    try:
        assert CmdRun()(args) == 0
    finally:
        os.chdir(old)
    second = _load(os.path.join(tmp, "rundir"))
    assert second["run"]["id"] != first["run"]["id"]
    assert second["result"].get("reused") is True
