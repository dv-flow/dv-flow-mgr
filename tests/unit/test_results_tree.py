"""The out/<run-id>/results/ link tree, staleness, retention, copy_logs."""
import json
import os
import shutil
import sys
import time

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.model import ResultNode, ResultsFile, RunInfo
from dv_flow.mgr.results.retention import prune
from dv_flow.mgr.results.summary import compute_summary
from dv_flow.mgr.results.tree import build_tree, safe_name

DATA = os.path.join(os.path.dirname(__file__), "data", "results")


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


def _rf(name):
    return ResultsFile.model_validate(json.load(open(os.path.join(DATA, name + ".json"))))


def test_layout_for_the_fail_fixture(tmp_path):
    root = build_tree(_rf("test-suite-fail"), str(tmp_path))
    case = os.path.join(root, "tests", "uvm-tests", "two-ch")
    assert sorted(os.listdir(case)) == ["STATUS", "log", "rundir", "waves.fst"]
    assert os.readlink(os.path.join(case, "log")) == "/abs/rundir/wb-dma-example.two-ch/sim.log"
    assert os.readlink(os.path.join(case, "waves.fst")) == "/abs/rundir/wb-dma-example.two-ch/waves.fst"
    assert os.readlink(os.path.join(case, "rundir")) == "/abs/rundir/wb-dma-example.two-ch"
    assert os.path.isfile(os.path.join(root, "tests", "STATUS"))


def test_leaf_links_its_rundir_entries(tmp_path):
    """A node's directory holds its run directory's files, not a `rundir`
    link to them -- a case and a suite alike."""
    rd = tmp_path / "rd"
    (rd / "sub").mkdir(parents=True)
    for f in ("sim.log", "waves.fst", "sim_stats.json", "STATUS", ".hidden"):
        (rd / f).write_text(f)
    art = lambda role, f: {"filetype": role, "basedir": str(rd), "files": [f],
                           "role": role}
    rf = _mk([{"name": "two-ch", "status": "fail", "rundir": str(rd),
               "artifacts": [art("log", "sim.log"), art("waves", "waves.fst"),
                             art("data", "sim_stats.json"),
                             {"filetype": "report", "basedir": "/elsewhere",
                              "files": ["r.txt"], "role": "report"}]}])
    rf.result.rundir = str(tmp_path / "suite-rd")
    (tmp_path / "suite-rd").mkdir()
    (tmp_path / "suite-rd" / "p.root.exec_data.json").write_text("{}")
    # an entry named like a child: the child's directory wins
    (tmp_path / "suite-rd" / "two-ch").mkdir()
    root = build_tree(rf, str(tmp_path / "out"))
    case = os.path.join(root, "root", "two-ch")
    assert sorted(os.listdir(case)) == [
        "STATUS", "log", "report-r.txt", "sim.log", "sim_stats.json", "sub", "waves.fst"]
    assert open(os.path.join(case, "STATUS")).read().startswith("fail")
    assert os.readlink(os.path.join(case, "sim.log")) == str(rd / "sim.log")
    assert os.readlink(os.path.join(case, "log")) == str(rd / "sim.log")
    assert os.path.isdir(os.path.join(case, "sub"))
    suite = os.path.join(root, "root")
    assert sorted(os.listdir(suite)) == ["STATUS", "p.root.exec_data.json", "two-ch"]
    assert not os.path.islink(os.path.join(suite, "two-ch"))
    assert os.readlink(os.path.join(suite, "p.root.exec_data.json")) == \
        str(tmp_path / "suite-rd" / "p.root.exec_data.json")


def test_no_failed_dir_when_nothing_failed(tmp_path):
    rf = _mk([{"name": "a", "status": "pass"}])
    rf.result.status = "pass"
    rf = ResultsFile(run=rf.run, summary=compute_summary(rf.result), result=rf.result)
    root = build_tree(rf, str(tmp_path))
    assert sorted(os.listdir(root)) == ["root"]


def test_failed_dir(tmp_path):
    root = build_tree(_rf("build-failure"), str(tmp_path))
    failed = os.path.join(root, "FAILED")
    assert sorted(os.listdir(failed)) == ["fw-build", "soc-dma-copy", "soc-dma-copy-two"]
    link = os.readlink(os.path.join(failed, "fw-build"))
    assert not os.path.isabs(link)
    assert os.path.realpath(os.path.join(failed, "fw-build")) == \
        os.path.realpath(os.path.join(root, "tests", "_tasks", "fw-build"))


def test_status_text(tmp_path):
    root = build_tree(_rf("test-suite-fail"), str(tmp_path))
    text = open(os.path.join(root, "tests", "uvm-tests", "two-ch", "STATUS")).read()
    assert text == ("fail: UVM_ERROR x2: ch1 dst mismatch @ 0x40\n"
                    "check uvm_errors: fail (uvm_errors=2, want == 0)\n")
    assert open(os.path.join(root, "tests", "uvm-tests", "smoke", "STATUS")).read() == "pass\n"


def test_report_label_and_synth_stages(tmp_path):
    root = build_tree(_rf("synth-timing-fail"), str(tmp_path))
    assert "report-Timing" in os.listdir(os.path.join(root, "synth"))
    assert os.path.islink(os.path.join(root, "synth", "pnr", "log"))
    assert os.listdir(os.path.join(root, "FAILED")) == ["synth"]


def _mk(children, name="root"):
    node = ResultNode.model_validate({"name": name, "status": "fail", "children": children})
    return ResultsFile(run=RunInfo(id="x"), summary=compute_summary(node), result=node)


def test_sanitize_and_collisions(tmp_path):
    rf = _mk([{"name": "a/b", "status": "fail"}, {"name": ".hidden", "status": "pass"},
              {"name": "dup", "status": "fail"}, {"name": "dup", "status": "fail"},
              {"name": "FAILED", "status": "pass"}])
    root = build_tree(rf, str(tmp_path))
    assert sorted(os.listdir(os.path.join(root, "root"))) == [
        "STATUS", "_FAILED", "a_b", "dup", "dup~2", "hidden"]
    assert sorted(os.listdir(os.path.join(root, "FAILED"))) == ["a_b", "dup", "dup~2"]
    assert safe_name("") == "_"


def test_internal_links_survive_a_move(tmp_path):
    out = tmp_path / "out" / "R1"
    build_tree(_rf("build-failure"), str(out))
    moved = tmp_path / "elsewhere"
    shutil.move(str(out), str(moved))
    f = moved / "results" / "FAILED" / "fw-build"
    assert os.path.isfile(f / "STATUS")


def test_no_symlinks_fallback(tmp_path, monkeypatch, caplog):
    def nope(*a, **k):
        raise OSError("not supported")
    monkeypatch.setattr(os, "symlink", nope)
    root = build_tree(_rf("test-suite-fail"), str(tmp_path))
    case = os.path.join(root, "tests", "uvm-tests", "two-ch")
    links = open(os.path.join(case, "LINKS.txt")).read()
    assert "log -> /abs/rundir/wb-dma-example.two-ch/sim.log" in links
    assert "rundir -> /abs/rundir/wb-dma-example.two-ch" in links
    assert "two-ch -> ../tests/uvm-tests/two-ch" in open(os.path.join(root, "FAILED", "LINKS.txt")).read()
    assert sum("symlinks are not supported" in r.getMessage() for r in caplog.records) == 1


def test_2000_leaves_fast(tmp_path):
    kids = [{"name": "s%d" % i, "status": "fail", "children": [
        {"name": "t%d" % j, "status": "fail" if j == 0 else "pass",
         "artifacts": [{"basedir": "/x/%d/%d" % (i, j), "files": ["sim.log"], "role": "log"}]}
        for j in range(100)]} for i in range(20)]
    rf = _mk(kids)
    t0 = time.time()
    build_tree(rf, str(tmp_path))
    assert time.time() - t0 < 2.0
    assert len(os.listdir(os.path.join(tmp_path, "results", "FAILED"))) == 20


# -- through dfm run ---------------------------------------------------------

FLOW = """
package:
  name: tr
  tasks:
  - name: hello
    shell: bash
    run: echo hello
"""


def _cli(tmp_path, *argv, config=None):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    (tmp_path / "flow.dv").write_text(FLOW)
    if config:
        (tmp_path / ".dfm").mkdir(exist_ok=True)
        (tmp_path / ".dfm" / "config.yaml").write_text(config)
    args = get_parser().parse_args(["run", "--root", str(tmp_path)] + list(argv))
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        return CmdRun()(args)
    finally:
        os.chdir(old)


def _show_json(tmp_path, capsys):
    capsys.readouterr()
    args = get_parser().parse_args(["show", "results", "--rundir", str(tmp_path / "rundir"),
                                    "--json"])
    assert args.func(args) == 0
    return json.loads(capsys.readouterr().out)


def test_run_builds_tree_and_no_results_tree(tmp_path):
    assert _cli(tmp_path, "tr.hello") == 0
    latest = tmp_path / "rundir" / "out" / "latest"
    assert os.path.islink(latest / "results" / "hello" / "log")
    assert _cli(tmp_path, "--no-results-tree", "tr.hello") == 0
    assert not os.path.exists(tmp_path / "rundir" / "out" / "latest" / "results")


def test_staleness(tmp_path, capsys):
    assert _cli(tmp_path, "tr.hello") == 0
    d = _show_json(tmp_path, capsys)
    st = d["result"]["artifacts"][0]["stamps"][0]
    assert st["state"] == "ok" and d["result"]["artifacts"][0]["stale"] is False
    log = st["path"]
    rec = open(tmp_path / "rundir" / "out" / "latest" / "results.json").read()
    with open(log, "a") as f:
        f.write("more\n")
    d = _show_json(tmp_path, capsys)
    assert d["result"]["artifacts"][0]["stamps"][0]["state"] == "stale"
    assert d["result"]["artifacts"][0]["stale"] is True
    os.remove(log)
    d = _show_json(tmp_path, capsys)
    assert d["result"]["artifacts"][0]["stamps"][0]["state"] == "missing"
    # the record itself is never rewritten
    assert open(tmp_path / "rundir" / "out" / "latest" / "results.json").read() == rec


def test_copy_logs(tmp_path):
    assert _cli(tmp_path, "tr.hello", config="results:\n  copy_logs: true\n") == 0
    latest = tmp_path / "rundir" / "out" / "latest"
    copied = latest / "logs" / "tr.hello" / "tr.hello.log"
    assert copied.is_file()
    assert os.path.realpath(latest / "results" / "hello" / "log") == os.path.realpath(copied)


# -- retention -----------------------------------------------------------------

def _mkrun(out, name, age):
    d = out / name
    d.mkdir(parents=True)
    (d / "results.json").write_text("{}")
    t = time.time() - age
    os.utime(d / "results.json", (t, t))
    return d


def test_retention_keep_previous(tmp_path):
    out = tmp_path / "out"
    for i in range(25):
        _mkrun(out, "20261031-1000%02d" % i, 1000 - i)        # i=24 is newest
    removed = prune(str(out), 19, "20261031-100024")
    assert sorted(removed) == ["20261031-1000%02d" % i for i in range(5)]
    assert len(os.listdir(out)) == 20


def test_retention_default_keeps_one_previous(tmp_path):
    out = tmp_path / "out"
    for i in range(4):
        _mkrun(out, "20261031-1000%02d" % i, 1000 - i)        # i=3 is newest
    prune(str(out), 1, "20261031-100003")
    assert sorted(os.listdir(out)) == ["20261031-100002", "20261031-100003"]
    prune(str(out), 0, "20261031-100003")
    assert sorted(os.listdir(out)) == ["20261031-100003"]


def test_retention_legacy_explicit_and_latest(tmp_path):
    out = tmp_path / "out"
    _mkrun(out, "0003", 5000)                     # legacy counter: prunable
    _mkrun(out, "ci-42", 9000)                    # explicit id: never pruned
    old_latest = _mkrun(out, "20261031-090000", 8000)
    os.symlink("20261031-090000", out / "latest")  # latest's target: never pruned
    for i in range(3):
        _mkrun(out, "20261031-1000%02d" % i, 100 - i)
    removed = prune(str(out), 1, "20261031-100002")
    assert sorted(removed) == ["0003", "20261031-100000"]
    left = sorted(os.listdir(out))
    assert "ci-42" in left and "20261031-090000" in left and "latest" in left


def test_retention_off(tmp_path):
    out = tmp_path / "out"
    for i in range(3):
        _mkrun(out, "20261031-1000%02d" % i, i)
    assert prune(str(out), None) == []


def test_2000_leaf_record_fast():
    from dv_flow.mgr.results.convert import to_dict
    d = {"name": "root", "children": [
        {"name": "s%d" % i, "children": [
            {"name": "t%d" % j, "status": "fail" if j == 0 else "pass",
             "diagnostics": [{"severity": "error", "msg": "e%d" % k} for k in range(15)],
             "metrics": {"walltime_s": 1.0}}
            for j in range(100)]} for i in range(20)]}
    t0 = time.time()
    node = ResultNode.model_validate(to_dict(d))
    rf = ResultsFile(run=RunInfo(id="x"), summary=compute_summary(node), result=node)
    text = json.dumps(rf.dump())
    assert time.time() - t0 < 2.0
    assert rf.summary.counts["total"] == 2000 and len(rf.summary.failures) == 20
    # capping keeps the record small: 10 diagnostics per leaf, not 15
    assert len(text) < 3_000_000
