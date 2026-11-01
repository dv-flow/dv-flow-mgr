"""results.api: check evaluation and finish()."""
import pytest

from dv_flow.mgr.results import api as R


@pytest.mark.parametrize("op,goal,expect", [
    (">=", 0, "pass"), (">=", 1, "fail"),
    ("<=", 0, "fail"), ("<=", 1, "pass"),
    ("==", 0.5, "pass"), ("==", 1, "fail"),
    ("!=", 1, "pass"), ("!=", 0.5, "fail"),
    (">", 0.4, "pass"), (">", 0.5, "fail"),
    ("<", 0.6, "pass"), ("<", 0.5, "fail"),
])
def test_eval_check_ops(op, goal, expect):
    c = R.eval_check({"m": {"value": 0.5}}, "c", "m", op, goal)
    assert c["status"] == expect
    assert c["value"] == 0.5


def test_eval_check_bare_number_metric():
    assert R.eval_check({"m": 3}, "c", "m", "<=", 3)["status"] == "pass"


def test_eval_check_missing_metric():
    c = R.eval_check({}, "c", "nope", ">=", 0)
    assert c["status"] == "error"
    assert "nope" in c["msg"]


def test_eval_check_bad_op():
    assert R.eval_check({"m": 1}, "c", "m", "~", 0)["status"] == "error"


def test_finish_failed_check():
    r = {"checks": [R.check("a", "pass"), R.eval_check({"w": 3}, "b", "w", "<=", 0)]}
    R.finish(r)
    assert r["status"] == "fail" and r["passed"] is False
    assert r["msg"].startswith("check b failed")


def test_finish_all_pass():
    r = {"checks": [R.check("a", "pass"), R.check("b", "skip")]}
    R.finish(r)
    assert r["status"] == "pass" and r["passed"] is True
    assert r.get("msg") is None


def test_finish_explicit_error_preserved():
    r = {"status": "error", "msg": "tool crashed", "checks": [R.check("a", "pass")]}
    R.finish(r)
    assert r["status"] == "error" and r["msg"] == "tool crashed"


def test_finish_counts():
    r = {"diagnostics": [{"severity": "error"}, {"severity": "warning"}, {"severity": "warning"}],
         "children": [{"status": "pass"}, {"status": "fail"},
                      {"children": [{"status": "notrun"}]}]}
    R.finish(r)
    assert r["counts"]["errors"] == 1 and r["counts"]["warnings"] == 2
    assert r["counts"]["total"] == 3
    assert r["counts"]["pass"] == 1 and r["counts"]["fail"] == 1 and r["counts"]["notrun"] == 1
    assert r["status"] == "fail"


def test_metric_helper():
    assert R.metric(3) == {"value": 3.0}
    assert R.metric(98.8, "MHz", "higher") == {"value": 98.8, "unit": "MHz", "better": "higher"}


def test_artifact_helper(tmp_path):
    class Ctxt:
        rundir = str(tmp_path)
        name = "p.t"
    a = R.artifact(Ctxt(), "lint.log", role="log", label="Lint log")
    assert a.basedir == str(tmp_path) and a.files == ["lint.log"]
    assert "role=log" in a.attributes and "label=Lint log" in a.attributes
    assert a.src == "p.t"


def test_mk_result():
    made = {}

    class Item:
        pass

    class Ctxt:
        name = "p.t"
        rundir = "/r"

        def mkDataItem(self, type, **kw):
            i = Item()
            i.type = type
            made["type"] = type
            return i
    r = R.mk_result(Ctxt(), "std.TestResult", name="case1", testname="t")
    assert r.type == "std.TestResult" and r.name == "case1"
    assert r.task == "p.t" and r.rundir == "/r" and r.testname == "t"


def test_artifact_without_ctxt(tmp_path):
    a = R.artifact(None, str(tmp_path / "x.log"), role="log")
    assert a.basedir == str(tmp_path) and a.files == ["x.log"] and "role=log" in a.attributes


def test_artifacts_walks_result_trees():
    from dv_flow.mgr.fileset import FileSet
    case = {"type": "std.TestResult", "name": "t1", "status": "fail", "checks": [],
            "children": [], "metrics": {}, "testname": "t1_test", "seed": 7,
            "artifacts": [FileSet(filetype="simTrace", basedir="/r", files=["w.fst"],
                                  attributes=["role=trace"]),
                          FileSet(filetype="simLog", basedir="/r", files=["sim.log"],
                                  attributes=["role=log"])]}
    root = {"type": "std.TestRunResult", "name": "tests", "status": "fail", "checks": [],
            "metrics": {}, "artifacts": [], "children": [case]}
    plain = FileSet(filetype="junk", basedir="/x", files=["y"])
    got = R.artifacts([root, plain], role="waves")
    assert len(got) == 1 and got[0].files == ["w.fst"]
    assert "result_path=tests/t1" in got[0].attributes
    assert "testname=t1_test" in got[0].attributes and "seed=7" in got[0].attributes
    assert "role=trace" in got[0].attributes          # legacy name matched
    assert [a.filetype for a in R.artifacts([root])] == ["simTrace", "simLog"]
    assert R.artifacts([root], filetype="simLog")[0].files == ["sim.log"]
    assert R.artifacts([plain]) == []
