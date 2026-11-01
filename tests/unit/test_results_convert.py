"""results.convert: data item -> ResultNode."""
import pytest

from dv_flow.mgr.fileset import FileSet
from dv_flow.mgr.results.convert import to_dict, to_node
from dv_flow.mgr.task_data import SeverityE, TaskMarker, TaskMarkerLoc


class _T:
    def __init__(self, name, uses=None):
        self.name = name
        self.uses = uses


_RES = _T("std.Result", _T("std.DataItem"))
_TEST = _T("std.TestResult", _RES)
_SUITE = _T("std.SuiteResult", _RES)
_HDL = _T("hdlsim.TestResult", _TEST)
_TYPES = {t.name: t for t in (_RES, _TEST, _SUITE, _HDL)}


def resolve(name):
    return _TYPES.get(name)


def test_lineage_order():
    n = to_node({"type": "hdlsim.TestResult", "name": "a", "status": "pass"}, resolve)
    assert n.types == ["hdlsim.TestResult", "std.TestResult", "std.Result"]


def test_unknown_type_lineage_ends_at_result():
    n = to_node({"type": "x.Mystery", "status": "pass"}, resolve)
    assert n.types == ["x.Mystery", "std.Result"]


def test_bare_metric_normalized():
    n = to_node({"status": "pass", "metrics": {
        "luts": 4211, "fmax_mhz": {"value": 98.8, "unit": "MHz", "better": "higher"},
        "simtime": "608us"}})
    assert n.metrics["luts"].value == 4211.0
    assert n.metrics["fmax_mhz"].unit == "MHz"
    assert n.metrics["fmax_mhz"].better == "higher"
    # Not a number: kept, as an attr
    assert "simtime" not in n.metrics
    assert n.attrs["simtime"] == "608us"


def test_diagnostic_capping():
    diags = []
    for i in range(20):
        diags.append({"severity": "warning", "msg": "w%d" % i})
    for i in range(5):
        diags.append({"severity": "error", "msg": "e%d" % i})
    n = to_node({"status": "fail", "diagnostics": diags})
    assert len(n.diagnostics) == 10
    assert n.counts["warnings"] == 20
    assert n.counts["errors"] == 5
    # errors first, in their original order
    assert [d.msg for d in n.diagnostics[:5]] == ["e0", "e1", "e2", "e3", "e4"]
    assert n.diagnostics[5].msg == "w0"


def test_producer_counts_win():
    n = to_node({"status": "fail", "counts": {"errors": 99},
                 "diagnostics": [{"severity": "error", "msg": "e"}]})
    assert n.counts["errors"] == 99


def test_marker_and_hdlsim_diagnostics():
    log = FileSet(filetype="simLog", basedir="/r", files=["sim.log"], attributes=["role=log"])
    m = TaskMarker(msg="boom", severity=SeverityE.Error,
                   loc=TaskMarkerLoc(path="/src/a.sv", line=3))
    n = to_node({"status": "fail", "artifacts": [log], "diagnostics": [
        m, {"severity": "error", "message": "SVA fail", "log_line": 42,
            "file": "/src/b.sv", "line": 7, "category": "assertion"}]})
    d0, d1 = n.diagnostics
    assert d0.msg == "boom" and d0.loc.path == "/src/a.sv" and d0.loc.line == 3
    assert d1.msg == "SVA fail"
    assert d1.loc.path == "/r/sim.log" and d1.loc.line == 42
    assert d1.src_loc.path == "/src/b.sv" and d1.src_loc.line == 7


def test_legacy_roles():
    arts = [FileSet(filetype="simTrace", basedir="/r", files=["w.fst"], attributes=["role=trace"]),
            FileSet(filetype="simStats", basedir="/r", files=["s.json"], attributes=["role=stats"]),
            FileSet(filetype="x", basedir="/r", files=["x"]),
            FileSet(filetype="r", basedir="/r", files=["t.rpt"], attributes=["role=report", "label=Timing"])]
    n = to_node({"status": "pass", "artifacts": arts})
    assert [a.role for a in n.artifacts] == ["waves", "data", "other", "report"]
    assert n.artifacts[3].label == "Timing"


def test_extra_fields_survive():
    n = to_node({"type": "hdlsim.TestResult", "status": "fail", "testname": "t1",
                 "seed": 7, "errors": 2, "seq": 3, "src": "pkg.check"}, resolve)
    d = n.model_dump()
    assert d["testname"] == "t1" and d["seed"] == 7 and d["errors"] == 2
    assert "seq" not in d
    assert d["task"] == "pkg.check"


def test_nested_child_keeps_lineage():
    n = to_node({"type": "std.SuiteResult", "name": "s", "children": [
        {"type": "hdlsim.TestResult", "name": "a", "status": "pass"},
        {"type": "std.Result", "name": "b", "status": "fail"}]}, resolve)
    assert n.types == ["std.SuiteResult", "std.Result"]
    assert n.children[0].types == ["hdlsim.TestResult", "std.TestResult", "std.Result"]
    assert n.children[1].types == ["std.Result"]
    # No explicit status: the worst child
    assert n.status == "fail"
    assert n.passed is False


def test_invalid_status_is_error():
    w = []
    n = to_node({"name": "x", "status": "bogus"}, warnings=w)
    assert n.status == "error"
    assert "bogus" in n.msg
    assert w and "bogus" in w[0]


def test_status_from_checks_and_passed():
    assert to_node({"checks": [{"name": "c", "status": "fail"}]}).status == "fail"
    assert to_node({"passed": True}).status == "pass"
    w = []
    assert to_node({}, warnings=w).status == "error"
    assert w


def test_legacy_suite_results_and_int_passed():
    d = to_dict({"type": "hdlsim.SuiteResult", "total": 2, "passed": 1, "failed": 1,
                 "results": [{"name": "a", "passed": True, "status": "pass"},
                             {"name": "b", "passed": False, "status": "fail"}]})
    assert [c["name"] for c in d["children"]] == ["a", "b"]
    assert d["status"] == "fail"
    assert d["passed"] is False
    assert d["npassed"] == 1
    assert "results" not in d


def test_legacy_report_cases():
    """Cases from hdlsim's report.json (the pre-std shape) convert cleanly."""
    import json
    import os
    p = os.path.join(os.path.dirname(__file__), "data", "results", "legacy-report.json")
    with open(p) as f:
        doc = json.load(f)
    nodes = [to_node(dict(c, type="hdlsim.TestResult"), resolve) for c in doc["cases"]]
    assert [n.status for n in nodes] == ["pass", "fail"]
    d = nodes[1].diagnostics[0]
    assert d.msg == "Assertion p_no_overrun failed"
    assert d.loc.line == 1873
    assert d.src_loc.path == "/abs/rtl/dma_ch.sv" and d.src_loc.line == 120
    assert nodes[1].model_dump()["errors"] == 2
