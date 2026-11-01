"""The MCP `dfm_get_results` tool: the same JSON as `dfm show results --json`."""
import asyncio
import json
import os
import shutil
import time

from dv_flow.mgr.cmds.agent.dfm_mcp_server import _dispatch, get_results

DATA = os.path.join(os.path.dirname(__file__), "data", "results")


def _rundir(tmp_path):
    out = tmp_path / "rundir" / "out"
    for i, (rid, fix) in enumerate((("20261031-100000", "test-suite-pass.json"),
                                    ("20261031-110000", "test-suite-fail.json"))):
        (out / rid).mkdir(parents=True)
        shutil.copy(os.path.join(DATA, fix), out / rid / "results.json")
        t = time.time() - 10 + i
        os.utime(out / rid / "results.json", (t, t))
    os.symlink("20261031-110000", out / "latest")
    return str(tmp_path / "rundir")


def test_failures_only_is_the_summary(tmp_path):
    rd = _rundir(tmp_path)
    d = json.loads(asyncio.run(_dispatch("dfm_get_results",
                                         {"rundir": rd, "failures_only": True}, None, None, None)))
    expect = json.load(open(os.path.join(DATA, "test-suite-fail.json")))["summary"]
    assert d == expect


def test_full_record_and_explicit_run(tmp_path):
    rd = _rundir(tmp_path)
    d = json.loads(get_results({"rundir": rd, "run": "20261031-100000"}))
    assert d["schema"] == "dvflow-results/1" and d["summary"]["status"] == "pass"
    # staleness is marked, as `show results --json` does
    st = d["result"]["children"][0]["children"][0]["artifacts"][0]["stamps"][0]
    assert st["state"] == "missing"


def test_default_rundir_is_the_builders(tmp_path):
    rd = _rundir(tmp_path)

    class B:
        rundir = rd
    d = json.loads(get_results({}, B()))
    assert d["summary"]["status"] == "fail"


def test_missing_record(tmp_path):
    d = json.loads(get_results({"rundir": str(tmp_path / "nope")}))
    assert "no results under" in d["error"]
