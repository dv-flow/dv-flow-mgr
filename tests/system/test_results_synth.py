"""The run-results format is domain-neutral: a synthesis flow (a fixture
package standing in for a synthesis library) records, renders and fails in
CI exactly like a test run, with no synthesis-specific code in dfm."""
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

import jsonschema
import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.model import results_json_schema

FIXTURE = os.path.join(os.path.dirname(__file__), "results_synth")


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


def _project(tmp_path):
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    return root


def _dfm(root, *argv):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    args = get_parser().parse_args(list(argv[:1]) + ["--root", str(root)] + list(argv[1:])) \
        if argv[0] == "run" else get_parser().parse_args(list(argv))
    old = os.getcwd()
    os.chdir(str(root))
    try:
        return args.func(args) if argv[0] != "run" else CmdRun()(args)
    finally:
        os.chdir(old)


def _record(root):
    with open(root / "rundir" / "out" / "latest" / "results.json") as f:
        return json.load(f)


def test_synth_record(tmp_path, capsys):
    root = _project(tmp_path)
    assert _dfm(root, "run", "--results-format", "junit", "synth") == 0   # failure is data
    d = _record(root)
    jsonschema.validate(d, results_json_schema())

    r = d["result"]
    assert r["type"] == "yosys.SynthResult" and r["types"] == ["yosys.SynthResult", "std.Result"]
    assert [c["name"] for c in r["children"]] == ["synth", "pnr"]
    assert r["metrics"]["fmax_mhz"] == {"value": 98.8, "unit": "MHz", "better": "higher",
                                        "label": "Fmax"}
    assert r["metrics"]["wns_ns"]["value"] == -0.121 and r["metrics"]["wns_ns"]["unit"] == "ns"
    assert r["metrics"]["luts"]["value"] == 4211

    s = d["summary"]
    assert s["status"] == "fail"
    assert s["msg"].startswith("timing not met: WNS -0.121 ns on clk_sys")
    assert len(s["failures"]) == 1
    f = s["failures"][0]
    assert f["path"] == "synth"
    assert [c["name"] for c in f["checks"]] == ["timing"]

    junit = ET.parse(str(root / "rundir" / "out" / "latest" / "junit.xml")).getroot()
    tc = {t.get("name"): t for t in junit.iter("testcase")}
    assert tc["timing"].find("failure") is not None
    assert tc["area"].find("failure") is None

    tree = root / "rundir" / "out" / "latest" / "results"
    assert os.path.islink(tree / "synth" / "pnr" / "log")
    assert os.path.isfile(tree / "synth" / "pnr" / "log")
    assert os.listdir(tree / "FAILED") == ["synth"]

    capsys.readouterr()
    assert _dfm(root, "show", "results", "--rundir", str(root / "rundir")) == 0
    out = capsys.readouterr().out
    assert "fmax_mhz=98.8 MHz" in out and "wns_ns=-0.121 ns" in out
    assert "check timing: fail (wns_ns=-0.121, want >= 0)" in out


def test_mixed_root_one_verdict(tmp_path):
    root = _project(tmp_path)
    assert _dfm(root, "run", "regress") == 0
    d = _record(root)
    jsonschema.validate(d, results_json_schema())
    r = d["result"]
    kinds = {c["name"]: c["types"][0] for c in r["children"]}
    assert kinds == {"tests": "std.TestRunResult", "synth": "yosys.SynthResult",
                     "bmc": "yosys.FormalResult"}
    assert r["status"] == "fail"                       # the synth timing check
    assert [f["path"] for f in d["summary"]["failures"]] == ["regress/synth"]


@pytest.mark.skipif(shutil.which("yosys") is None, reason="yosys not installed")
def test_real_yosys(tmp_path):
    root = _project(tmp_path)
    assert _dfm(root, "run", "-D", "real=true", "synth") == 0
    d = _record(root)
    jsonschema.validate(d, results_json_schema())
    assert d["result"]["children"][0]["metrics"]["cells"]["value"] > 0


def _code_words(path):
    """Identifiers and non-docstring string literals of a module: what its
    code can branch on (comments and docstrings are prose)."""
    import ast
    tree = ast.parse(open(path).read())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant):
                docs.add(id(body[0].value))
    words = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            words.append(node.value)
        elif isinstance(node, ast.Name):
            words.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
    return words


def test_no_profile_branches_in_dfm():
    """Domain-neutral: dfm's results code never names a synthesis, formal or
    simulator type. (The test profile, std.TestResult/SuiteResult, is named
    only where test cases are mapped: the JUnit/CTRF renderer and the
    recorder's completion of a test runner's selection.)"""
    import dv_flow.mgr.results as pkg
    d = os.path.dirname(pkg.__file__)
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".py"):
            continue
        for w in _code_words(os.path.join(d, fn)):
            for bad in ("SynthResult", "FormalResult", "yosys", "sby", "hdlsim"):
                assert bad not in w, (fn, w)
    for fn in sorted(os.listdir(d)):
        # render_junit maps test cases; the recorder completes a test
        # runner's selection with notrun cases
        if fn.endswith(".py") and fn not in ("render_junit.py", "lineage.py", "recorder.py"):
            for w in _code_words(os.path.join(d, fn)):
                assert "std.TestResult" not in w and "std.SuiteResult" not in w, (fn, w)
