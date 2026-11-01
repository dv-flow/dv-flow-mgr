"""std.EvalRunner: trials (epochs), their reduction to a case verdict, the run
record, and the Inspect eval-set log."""
import glob
import json
import os
import re
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


GRADER = """
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.results import api as R
from dv_flow.mgr.std.eval_sample import sample_result

async def Grade(ctxt, input):
    p = input.params
    s = R.mk_result(ctxt, "std.EvalSample", name=p.label)
    if p.pass_epoch:
        score = 1.0 if p.epoch == p.pass_epoch else 0.0
    else:
        score = p.score / 100.0
    s.scores = {"match": {"value": score}}
    s.output = "answer %d" % p.epoch
    s.model_usage = {p.model: {"input_tokens": 10, "output_tokens": 5,
                               "total_tokens": 15}}
    sample_result(s, thresholds={"match": 0.5})
    return TaskDataResult(output=[s])
"""

BASE = """
package:
  name: ev
  tasks:
  - name: case
    shell: pytask
    run: grader.py::Grade
    with:
      label: {type: str, value: ""}
      score: {type: int, value: 0}
      pass_epoch: {type: int, value: 0}
      epoch: {type: int, value: 1}
      model: {type: str, value: "anthropic/claude"}
"""


def _case(name, score=0, pass_epoch=0, extra="", tag="std.Eval", model=""):
    w = "label: %s, score: %d, pass_epoch: %d" % (name, score, pass_epoch)
    if model:
        w += ", model: %s" % model
    return """
  - name: %s
    uses: case
    tags: [{%s: {name: %s%s}}]
    with: {%s}
""" % (name, tag, name, (", benchmark: bench" + extra) if tag == "std.Eval" else extra, w)


def _root(needs, epochs=1, reducer="mean", extra=""):
    return """
  - root: evals
    uses: std.EvalRunner
    with: {epochs: %d, epochs_reducer: %s%s}
    needs: [%s]
""" % (epochs, reducer, extra, ", ".join(needs))


THREE = _case("s1", 100) + _case("s2", 25) + _case("s3", pass_epoch=2,
                                                   extra=", sample_id: q3")


def _run(tmp_path, flow, *extra, after=()):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    (tmp_path / "flow.dv").write_text(BASE + flow)
    (tmp_path / "grader.py").write_text(GRADER)
    args, task_args = get_parser().parse_known_args(
        ["run", "--root", str(tmp_path)] + list(extra) + ["evals"] + list(after))
    args.task_args = task_args
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        rc = CmdRun()(args)
    finally:
        os.chdir(old)
    return rc


def _record(tmp_path):
    out = tmp_path / "rundir" / "out" / "latest"
    return json.load(open(out / "results.json"))


def _logs(tmp_path):
    return sorted(glob.glob(str(tmp_path / "rundir" / "ev.evals" / "logs" / "*")))


def test_sample_result_helper():
    from dv_flow.mgr.std.eval_sample import sample_result

    class S:
        pass
    s = S()
    s.scores = {"acc": {"value": 0.4}, "ok": {"value": True}, "note": {"value": "x"}}
    s.status = ""
    s.error = ""
    s.id = "q1"
    s.epoch = 2
    sample_result(s, thresholds={"acc": 0.5})
    assert s.metrics["score_acc"] == {"value": 0.4, "better": "higher", "label": "acc"}
    assert s.metrics["score_ok"]["value"] == 1.0 and "score_note" not in s.metrics
    assert s.checks[0]["name"] == "acc" and s.checks[0]["status"] == "fail"
    assert s.status == "fail" and s.passed is False
    assert s.attrs == {"id": "q1", "epoch": 2}
    s2 = S()
    s2.scores, s2.status, s2.error, s2.id, s2.epoch = {}, "", "agent crashed\nmore", "", 1
    sample_result(s2)
    assert s2.status == "error" and s2.msg == "agent crashed"


def test_evals_root_record_and_ctrf(tmp_path):
    """epochs=1: each sample is a case; the record, CTRF and log agree."""
    rc = _run(tmp_path, _case("s1", 100) + _case("s2", 25) + _root(["s1", "s2"]),
              "--results-format", "ctrf")
    assert rc == 0
    d = _record(tmp_path)
    r = d["result"]
    assert r["type"] == "std.TestRunResult"
    kids = {c["name"]: c for c in r["children"]}
    assert set(kids) == {"s1", "s2"}
    assert kids["s1"]["types"] == ["std.EvalSample", "std.TestResult", "std.Result"]
    assert kids["s2"]["status"] == "fail"
    # the trials keep their bare names at epochs=1
    assert kids["s1"]["task"] == "ev.s1"
    ctrf = json.load(open(tmp_path / "rundir" / "out" / "latest" / "ctrf.json"))
    tests = {t["name"]: t for t in ctrf["results"]["tests"]}
    assert set(tests) == {"s1", "s2"}
    assert tests["s1"]["status"] == "passed" and tests["s2"]["status"] == "failed"
    assert tests["s2"]["extra"]["score_match"] == 0.25
    logs = _logs(tmp_path)
    assert len(logs) == 1
    log = json.load(open(logs[0]))
    assert log["eval"]["config"]["epochs"] == 1 and "reductions" not in log
    assert [(s["id"], s["epoch"]) for s in log["samples"]] == [("s1", 1), ("s2", 1)]


def test_epochs_replicate_and_reduce(tmp_path, capsys):
    rc = _run(tmp_path, THREE + _root(["s1", "s2", "s3"], epochs=3,
                                      reducer="pass_at_k"))
    assert rc == 0
    rd = tmp_path / "rundir"
    for c in ("s1", "s2", "s3"):
        for e in (1, 2, 3):
            assert (rd / ("ev.%s.e%d" % (c, e))).is_dir()
        assert not (rd / ("ev.%s" % c)).exists()

    d = _record(tmp_path)
    r = d["result"]
    kids = {c["name"]: c for c in r["children"]}
    # One leaf per case, whatever the epoch count
    assert set(kids) == {"s1", "s2", "s3"}
    assert r["counts"]["total"] == 3 and r["counts"]["fail"] == 1
    s3 = kids["s3"]
    assert s3["type"] == "std.EvalCase" and s3["status"] == "pass"
    # the epoch reached the grader: only trial 2 passed
    assert [(t["epoch"], t["status"]) for t in s3["trials"]] == [
        (1, "fail"), (2, "pass"), (3, "fail")]
    assert s3["metrics"]["trials_passed"]["value"] == 1
    assert s3["msg"] == "1/3 trials passed (pass_at_k)"
    assert kids["s2"]["status"] == "fail"
    assert kids["s2"]["checks"][0]["name"] == "pass_at_k"
    assert [f["path"] for f in d["summary"]["failures"]] == ["evals/s2"]
    # roll-up: verdicts average, trial counts sum
    assert d["summary"]["metrics"]["trials_passed"]["value"] == 4

    logs = _logs(tmp_path)
    assert len(logs) == 1
    name = os.path.basename(logs[0])
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}.*_bench_[0-9a-f]+\.json$", name)
    log = json.load(open(logs[0]))
    assert log["eval"]["eval_set_id"] == d["run"]["id"]
    assert log["eval"]["model"] == "anthropic/claude"
    assert log["eval"]["config"] == {"epochs": 3, "epochs_reducer": ["pass_at_3"]}
    assert log["eval"]["dataset"]["sample_ids"] == ["q3", "s1", "s2"]
    assert len(log["samples"]) == 9
    assert log["results"]["total_samples"] == 9
    red = {s["sample_id"]: s["value"] for s in log["reductions"][0]["samples"]}
    assert red == {"q3": 1.0, "s1": 1.0, "s2": 1.0}
    assert log["stats"]["model_usage"]["anthropic/claude"]["total_tokens"] == 135
    assert "Eval logs:" in capsys.readouterr().out.replace("\n", "")


@pytest.mark.parametrize("reducer,status", [
    ("pass_at_k", "pass"), ("max", "pass"), ("mean", "fail"),
    ("median", "fail"), ("all", "fail"), ("min", "fail")])
def test_reducer_decides_case_verdict(tmp_path, reducer, status):
    _run(tmp_path, _case("s3", pass_epoch=2) + _root(["s3"], epochs=3, reducer=reducer))
    kids = {c["name"]: c for c in _record(tmp_path)["result"]["children"]}
    assert kids["s3"]["status"] == status
    assert kids["s3"]["checks"][0]["name"] == reducer


def test_trials_are_never_uptodate(tmp_path):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    _run(tmp_path, _case("s1", 100) + _root(["s1"], epochs=2))
    stamp = (tmp_path / "rundir" / "ev.s1.e1" / "sample.out")
    stamp.write_text("stale")
    _run(tmp_path, _case("s1", 100) + _root(["s1"], epochs=2))
    d = _record(tmp_path)
    kids = {c["name"]: c for c in d["result"]["children"]}
    assert [t["epoch"] for t in kids["s1"]["trials"]] == [1, 2]
    assert not any(n.get("reused") for n in d["result"]["children"])


def test_ordinary_tests_are_not_replicated(tmp_path):
    flow = _case("s1", 100) + _case("t1", 100, tag="std.Test") + \
        _root(["s1", "t1"], epochs=2)
    assert _run(tmp_path, flow) == 0
    rd = tmp_path / "rundir"
    assert (rd / "ev.t1").is_dir() and not (rd / "ev.t1.e1").exists()
    assert (rd / "ev.s1.e1").is_dir() and (rd / "ev.s1.e2").is_dir()
    kids = {c["name"]: c for c in _record(tmp_path)["result"]["children"]}
    assert kids["t1"]["type"] == "std.EvalSample" and kids["s1"]["type"] == "std.EvalCase"


def test_cases_in_a_suite_are_reduced_in_place(tmp_path):
    flow = _case("s1", 100) + _case("s2", 25) + """
  - name: grp
    uses: std.TestSuite
    needs: [s1, s2]
""" + _root(["grp"], epochs=2)
    assert _run(tmp_path, flow) == 0
    r = _record(tmp_path)["result"]
    assert r["counts"]["total"] == 2 and r["counts"]["fail"] == 1
    grp = {c["name"]: c for c in r["children"]}["grp"]
    assert [(c["name"], c["type"]) for c in grp["children"]] == [
        ("s1", "std.EvalCase"), ("s2", "std.EvalCase")]
    assert grp["counts"]["total"] == 2


def test_selection_applies_to_eval_cases(tmp_path):
    _run(tmp_path, THREE + _root(["s1", "s2", "s3"], epochs=2), after=["--tests", "s1"])
    kids = [c["name"] for c in _record(tmp_path)["result"]["children"]]
    assert kids == ["s1"]
    assert not (tmp_path / "rundir" / "ev.s2.e1").exists()


def test_bad_epochs_is_an_error(tmp_path):
    try:
        rc = _run(tmp_path, _case("s1", 100) + _root(["s1"], epochs=0))
    except SystemExit as e:
        rc = e.code
    assert rc != 0


def test_unknown_reducer_is_rejected(tmp_path, capsys):
    assert _run(tmp_path, _case("s1", 100) + _root(["s1"], reducer="bogus")) != 0
    assert "not a valid value" in capsys.readouterr().err
    assert not _logs(tmp_path)


def test_mixed_models_in_one_log_fail_the_root(tmp_path):
    flow = _case("s1", 100) + _case("s2", 100, model="openai/gpt") + _root(["s1", "s2"])
    _run(tmp_path, flow)
    d = _record(tmp_path)
    assert d["summary"]["status"] == "error"
    assert "spans several models" in d["result"]["msg"]
    assert not _logs(tmp_path)


def test_eval_format_needs_inspect_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    _run(tmp_path, _case("s1", 100) + _root(["s1"], extra=", log_format: eval"))
    d = _record(tmp_path)
    assert d["summary"]["status"] == "error" and "inspect" in d["result"]["msg"]


def test_log_dir_holds_only_this_runs_logs(tmp_path):
    _run(tmp_path, _case("s1", 100) + _root(["s1"]))
    first = _logs(tmp_path)
    _run(tmp_path, _case("s1", 100) + _root(["s1"]))
    second = _logs(tmp_path)
    assert len(first) == len(second) == 1


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------

def test_score_value_fallbacks():
    from dv_flow.mgr.std.eval_sample import score_value
    assert score_value({"scores": {"a": {"value": 0.3}}}) == 0.3
    assert score_value({"scores": {"a": {"value": True}, "b": {"value": 0.1}}}, "a") == 1.0
    assert score_value({"scores": {}, "status": "pass"}) == 1.0
    assert score_value({"scores": {"a": {"value": 0.3}, "b": {"value": 0.1}},
                        "status": "fail"}) == 0.0


def test_reducers():
    from dv_flow.mgr.std.eval_sample import ReducerError, reduce_scores
    assert reduce_scores([0.0, 1.0, 0.0], "pass_at_k") == 1.0
    assert reduce_scores([1.0, 1.0, 0.0], "all") == 0.0
    assert reduce_scores([0.2, 0.4, 0.9], "median") == 0.4
    with pytest.raises(ReducerError):
        reduce_scores([], "mean")
    with pytest.raises(ReducerError):
        reduce_scores([1.0], "nope")


def test_epoch_names():
    from dv_flow.mgr.std.eval_select import EpochError, check_epochs, epoch_name
    assert epoch_name("p.c", 1, 1) == "p.c"
    assert epoch_name("p.c", 2, 3) == "p.c.e2"
    assert check_epochs(4) == 4
    for bad in (0, -1, "x", 1.5):
        with pytest.raises(EpochError):
            check_epochs(bad)


def test_sample_io(tmp_path):
    from dv_flow.mgr.std.eval_sample import (read_trajectory, sample_to_inspect,
                                             write_sample)
    s = {"type": "std.EvalSample", "id": "q", "epoch": 2, "input": "hi",
         "output": "yo", "scores": {"m": {"value": 1.0}}, "error": "boom",
         "events": "t.jsonl", "model_usage": {"m/x": {"total_tokens": 3}}}
    p = write_sample(str(tmp_path), s)
    assert json.load(open(p))["id"] == "q"
    d = sample_to_inspect(s)
    assert d["output"]["model"] == "m/x" and d["output"]["completion"] == "yo"
    assert d["error"]["message"] == "boom"
    assert d["metadata"]["transcript"] == "t.jsonl" and d["events"] == []
    (tmp_path / "t.jsonl").write_text('{"role": "meta"}\n{"role": "user"}\n')
    assert [r["role"] for r in read_trajectory(str(tmp_path), "t.jsonl")] == ["meta", "user"]
    (tmp_path / "t.json").write_text('[{"role": "meta"}]')
    assert read_trajectory(str(tmp_path), "t.json") == [{"role": "meta"}]


def test_log_dir_must_stay_in_the_rundir(tmp_path):
    from dv_flow.mgr.std.eval_log import LogWriteError, write_log_dir
    for bad in ("/abs", "../out"):
        with pytest.raises(LogWriteError):
            write_log_dir(str(tmp_path), [], log_dir=bad, log_format="json")


def test_log_validates_with_inspect(tmp_path):
    """The assembled log is an Inspect EvalLog (when inspect_ai is here)."""
    pytest.importorskip("inspect_ai")
    from inspect_ai.log import list_eval_logs, read_eval_log
    _run(tmp_path, THREE + _root(["s1", "s2", "s3"], epochs=3, reducer="pass_at_k"))
    logs = list_eval_logs(str(tmp_path / "rundir" / "ev.evals" / "logs"))
    assert len(logs) == 1
    log = read_eval_log(logs[0])
    assert log.eval.task == "bench" and len(log.samples) == 9
