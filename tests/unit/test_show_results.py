"""`dfm show results` over the shared fixtures."""
import json
import os
import shutil
import time

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.results.model import ResultsFile
from dv_flow.mgr.results.render_text import render_tree

DATA = os.path.join(os.path.dirname(__file__), "data", "results")


def _rundir(tmp_path, records):
    """A rundir holding `records` [(run_id, fixture)], oldest first; `latest`
    points at the last one."""
    rundir = tmp_path / "rundir"
    out = rundir / "out"
    out.mkdir(parents=True)
    t = time.time() - 100
    for i, (rid, fix) in enumerate(records):
        d = out / rid
        d.mkdir()
        p = d / "results.json"
        doc = json.load(open(os.path.join(DATA, fix)))
        doc["run"]["id"] = rid
        p.write_text(json.dumps(doc))
        os.utime(p, (t + i, t + i))
    if records:
        os.symlink(records[-1][0], out / "latest")
    return str(rundir)


def _show(capsys, *argv):
    args = get_parser().parse_args(["show", "results"] + list(argv))
    rc = args.func(args)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


RECS = [("20261031-100000", "test-suite-pass.json"),
        ("20261031-110000", "synth-timing-fail.json"),
        ("20261031-120000", "test-suite-fail.json")]


def test_list_newest_first(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    rc, out, _ = _show(capsys, "--rundir", rd, "--list")
    assert rc == 0
    ids = [l.split()[0] for l in out.strip().splitlines()]
    assert ids == ["20261031-120000", "20261031-110000", "20261031-100000"]
    assert "FAIL" in out.splitlines()[0]


def test_list_json(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    rc, out, _ = _show(capsys, "--rundir", rd, "--list", "--json")
    rows = json.loads(out)
    assert [r["id"] for r in rows][0] == "20261031-120000"
    assert rows[1]["status"] == "fail" and rows[2]["status"] == "pass"


def test_latest_vs_explicit(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    _, out, _ = _show(capsys, "--rundir", rd, "--json")
    assert json.loads(out)["run"]["id"] == "20261031-120000"
    _, out, _ = _show(capsys, "--rundir", rd, "--run", "latest", "--json")
    assert json.loads(out)["run"]["id"] == "20261031-120000"
    _, out, _ = _show(capsys, "--rundir", rd, "--run", "20261031-100000", "--json")
    assert json.loads(out)["run"]["id"] == "20261031-100000"


def test_missing_latest_link_uses_newest(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    os.remove(os.path.join(rd, "out", "latest"))
    _, out, _ = _show(capsys, "--rundir", rd, "--json")
    assert json.loads(out)["run"]["id"] == "20261031-120000"


def test_json_failures_is_summary(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    rc, out, _ = _show(capsys, "--rundir", rd, "--json", "--failures")
    assert rc == 0
    expect = json.load(open(os.path.join(DATA, "test-suite-fail.json")))["summary"]
    assert json.loads(out) == expect


def test_json_marks_missing_artifacts(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    _, out, _ = _show(capsys, "--rundir", rd, "--json")
    d = json.loads(out)
    two = d["result"]["children"][0]["children"][1]
    assert two["artifacts"][0]["stamps"][0]["state"] == "missing"
    assert two["artifacts"][0]["stale"] is True


@pytest.mark.parametrize("fix", ["test-suite-pass", "test-suite-fail", "synth-timing-fail"])
def test_text_snapshot(fix):
    rf = ResultsFile.model_validate(json.load(open(os.path.join(DATA, fix + ".json"))))
    with open(os.path.join(DATA, "text", fix + ".txt")) as f:
        assert render_tree(rf) == f.read()


def test_text_command(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    rc, out, _ = _show(capsys, "--rundir", rd)
    assert rc == 0
    assert "two-ch  FAIL" in out
    assert "check uvm_errors: fail" in out
    assert "sim.log:1873 [missing]" in out
    rc, out, _ = _show(capsys, "--rundir", rd, "--failures")
    assert out.splitlines()[0].startswith("FAIL: 1 of 2 failed")
    assert "tests/uvm-tests/two-ch" in out


def test_depth(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    _, out, _ = _show(capsys, "--rundir", rd, "--depth", "1")
    assert "uvm-tests  FAIL" in out
    assert "two-ch" not in out
    assert "... 2 more" in out


def test_missing_rundir(tmp_path, capsys):
    rc, out, err = _show(capsys, "--rundir", str(tmp_path / "nope"))
    assert rc == 1
    assert "no results under" in err and "dfm run" in err
    rc, _, err = _show(capsys, "--rundir", str(tmp_path / "nope"), "--list")
    assert rc == 1


def test_unknown_run(tmp_path, capsys):
    rd = _rundir(tmp_path, RECS)
    rc, _, err = _show(capsys, "--rundir", rd, "--run", "19990101-000000")
    assert rc == 1 and "19990101-000000" in err
