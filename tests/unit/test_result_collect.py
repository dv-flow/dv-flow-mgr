"""std.ResultCollect / std.TestSuite / std.TestRunner roll-ups, and the
results.rollup rules they use."""
import asyncio
import json
import os
import sys

import pytest

from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.recorder import ResultsRecorder
from dv_flow.mgr.results.rollup import metric_rule, rollup, rollup_metrics
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


# -- rollup rules --------------------------------------------------------------

def test_metric_rules():
    assert metric_rule("walltime_s") == "sum"          # registry
    assert metric_rule("maxrss_mb") == "max"
    assert metric_rule("fmax_mhz") == "min"
    assert metric_rule("cov_line_pct") == "max"         # family wildcard
    assert metric_rule("my_time", "lower") == "sum"    # unregistered, by direction
    assert metric_rule("my_score", "higher") == "min"
    assert metric_rule("my_label", "none") == "none"
    assert metric_rule("my_unknown") == "none"


def test_rollup_metrics():
    kids = [{"metrics": {"walltime_s": {"value": 2, "unit": "s", "better": "lower"},
                         "fmax_mhz": {"value": 98.8, "unit": "MHz", "better": "higher"},
                         "tag": {"value": 1, "better": "none"}, "luts": 10}},
            {"metrics": {"walltime_s": {"value": 3}, "fmax_mhz": {"value": 120.0},
                         "tag": {"value": 2}, "luts": 20}}]
    m = rollup_metrics(kids)
    assert m["walltime_s"] == {"value": 5.0, "unit": "s", "better": "lower"}
    assert m["fmax_mhz"]["value"] == 98.8                # conservative
    assert "tag" not in m                                 # better: none
    assert m["luts"]["value"] == 30.0                     # registry: sum


def test_rollup_metrics_detail_spread():
    kids = [{"metrics": {"walltime_s": 1.0, "maxrss_mb": 10.0}},
            {"metrics": {"walltime_s": 3.0, "maxrss_mb": 30.0}}]
    m = rollup_metrics(kids, detail=True)
    assert m["walltime_s"]["value"] == 4.0
    assert m["walltime_s_max"]["value"] == 3.0
    assert m["walltime_s_mean"]["value"] == 2.0
    assert "maxrss_mb" not in m and m["maxrss_mb_max"]["value"] == 30.0


def test_rollup_mixed_children():
    kids = [{"type": "std.TestResult", "status": "pass"},
            {"type": "yosys.SynthResult", "status": "fail",
             "children": [{"status": "pass"}, {"status": "pass"}]},
            {"type": "std.TaskResult", "status": "error"}]
    status, counts, _ = rollup(kids)
    assert status == "error"
    assert counts["total"] == 4                           # by leaf
    assert counts["pass"] == 3 and counts["error"] == 1


def test_rollup_empty():
    status, counts, metrics = rollup([])
    assert status == "notrun" and counts["total"] == 0 and metrics == {}


# -- the tasks -----------------------------------------------------------------

TASK_PY = '''
from dv_flow.mgr import TaskDataResult, FileSet
from dv_flow.mgr.results import api as R

async def Case(ctxt, input):
    p = input.params
    res = R.mk_result(ctxt, p.rtype, name=p.label, status=p.status,
                      metrics={"walltime_s": R.metric(p.wall, name="walltime_s")})
    R.finish(res)
    extra = FileSet(filetype="junk", basedir=input.rundir, files=[])
    return TaskDataResult(output=[res, extra])
'''


def _case(name, status="pass", rtype="std.TestResult", wall=1.0):
    return """
  - name: %s
    shell: pytask
    run: task.py::Case
    tags: [{std.Test: {name: %s}}]
    with:
      label: {type: str, value: "%s"}
      status: {type: str, value: "%s"}
      rtype: {type: str, value: "%s"}
      wall: {type: float, value: %s}
""" % (name, name, name, status, rtype, wall)


FLOW = """
package:
  name: rc
  tasks:
""" + _case("a") + _case("b", "fail", wall=2.0) + _case("c") + _case(
    "syn", "fail", "std.Result", 5.0) + """
  - name: inner
    uses: std.TestSuite
    needs: [b, c]
  - name: outer
    uses: std.TestSuite
    needs: [a, inner]
  - name: tests
    uses: std.TestRunner
    needs: [outer]
  - name: regress
    uses: std.ResultCollect
    needs: [tests, syn]
    with:
      checks:
      - {name: all_pass, metric: fail, op: "==", goal: 0}
      - {name: fast, metric: walltime_s, op: "<=", goal: 100}
  - name: nothing
    uses: std.ResultCollect
    needs: [plain]
  - name: plain
    shell: bash
    run: echo hi
"""


def _run(tmp_path, task):
    (tmp_path / "flow.dv").write_text(FLOW)
    (tmp_path / "task.py").write_text(TASK_PY)
    rundir = str(tmp_path / "rundir")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    b = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir, builder=b, nproc=2)
    node = b.mkTaskNode(task)
    rec = ResultsRecorder(runner, [node], rundir, b.run_id)
    runner.add_event_listener(rec.event)
    asyncio.run(runner.run(node))
    assert runner.status == 0
    rf = rec.record()
    return node, json.load(open(rec.path))


def _types(out):
    return [getattr(i, "type", None) for i in out.output]


def test_nested_suites_and_runner(tmp_path):
    node, d = _run(tmp_path, "rc.tests")
    r = d["result"]
    assert r["type"] == "std.TestRunResult" and r["name"] == "tests"
    assert r["types"] == ["std.TestRunResult", "std.SuiteResult", "std.Result"]
    (outer,) = r["children"]
    assert outer["type"] == "std.SuiteResult" and outer["name"] == "outer"
    assert [c["name"] for c in outer["children"]] == ["a", "inner"]
    inner = outer["children"][1]
    assert [c["name"] for c in inner["children"]] == ["b", "c"]
    assert inner["status"] == "fail" and outer["status"] == "fail" and r["status"] == "fail"
    assert inner["total"] == 2 and inner["failed"] == 1
    assert r["counts"]["total"] == 3 and r["counts"]["fail"] == 1
    assert r["metrics"]["walltime_s"]["value"] == 4.0
    assert r["msg"] == "1 of 3 failed"
    # The members' own items still pass through
    assert _types(node.output).count("std.FileSet") == 3
    s = d["summary"]
    assert [f["path"] for f in s["failures"]] == ["tests/outer/inner/b"]


def test_result_collect_mixed_with_checks(tmp_path):
    node, d = _run(tmp_path, "rc.regress")
    # Not a passthrough: one node out
    assert _types(node.output) == ["std.Result"]
    r = d["result"]
    assert [c["name"] for c in r["children"]] == ["tests", "syn"]
    assert r["status"] == "fail"
    checks = {c["name"]: c for c in r["checks"]}
    assert checks["all_pass"]["status"] == "fail" and checks["all_pass"]["value"] == 2
    assert checks["fast"]["status"] == "pass" and checks["fast"]["value"] == 9.0
    assert r["counts"]["total"] == 4


def test_result_collect_empty(tmp_path):
    node, d = _run(tmp_path, "rc.nothing")
    r = d["result"]
    assert r["status"] == "notrun" and r["msg"] == "no results"
    assert _types(node.output) == ["std.Result"]


def test_suite_without_results_emits_nothing(tmp_path):
    flow = """
package:
  name: rs
  tasks:
  - name: t1
    shell: bash
    run: echo hi
  - name: s
    uses: std.TestSuite
    needs: [t1]
"""
    (tmp_path / "flow.dv").write_text(flow)
    rundir = str(tmp_path / "rundir")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    b = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir, builder=b, nproc=2)
    node = b.mkTaskNode("rs.s")
    asyncio.run(runner.run(node))
    assert runner.status == 0
    assert "std.SuiteResult" not in _types(node.output)
