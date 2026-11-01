#****************************************************************************
#* eval_log.py
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#****************************************************************************
"""Assembling the eval set: `summary:` for `std.EvalRunner`.

The samples arrive the way test verdicts already do -- through ordinary
dataflow, at the root, once everything has run. The root's run body
(`EvalRunnerRun`) stamps each sample with its trial's identity, reduces a
replicated case's trials to one verdict (`std.EvalCase`), groups the samples
into Inspect `EvalLog` documents and writes the log directory. The `summary:`
hook only reports it: writing the eval set in a task is what lets a write
failure fail the run.

The grouping is forced by Inspect's own scope rule: an `EvalLog` covers one
task and one model, so a run spanning several views cannot be one log. What
makes them one *thing* is `eval_set_id`, shared across the directory --
Inspect's native mechanism for exactly this, and the unit `list_eval_logs()`
and the viewer consume. Mapping it to the DFM run-id makes a run and an eval
set the same object without either system knowing about the other.

`.json` is written directly. `.eval` is a zip-based binary format with no
published byte-level layout -- the documentation points readers at `inspect
log dump` rather than at a spec -- so producing it means running the Inspect
CLI, which is an optional PATH dependency here and never an import.
"""

import dataclasses as dc
import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .eval_sample import (REDUCERS, ReducerError, _as_dict, _get,
                          reduce_scores, sample_to_inspect, score_value,
                          trial_passed)

_log = logging.getLogger("eval_log")

# Bumped when the assembled layout changes incompatibly. Tracks Inspect's
# `EvalLog.version`, which is what a consumer actually validates against.
INSPECT_LOG_VERSION = 2

SAMPLE_TYPE = "std.EvalSample"
CASE_TYPE = "std.EvalCase"


class LogWriteError(Exception):
    """The eval set could not be written. Raised rather than warned: a
    benchmark run whose results went nowhere has produced nothing, and
    reporting success for it is worse than failing."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def is_sample(item) -> bool:
    """Is `item` a `std.EvalSample` (or derived from one)? Structural, like
    the test report: a project may derive its own sample type."""
    t = _get(item, "type")
    if t == SAMPLE_TYPE:
        return True
    return all(_has(item, k) for k in ("scores", "epoch", "input", "status"))


def _has(item, key) -> bool:
    return key in item if isinstance(item, dict) else hasattr(item, key)


def trial_for(sample, trials) -> Optional[Any]:
    """The `eval_select.Trial` whose node produced `sample` -- the node
    itself, or (for a compound case) a task in its body."""
    task = _get(sample, "task") or _get(sample, "src") or ""
    if not task or not trials:
        return None
    if task in trials:
        return trials[task]
    best = None
    for name in trials:
        if task.startswith(name + ".") and (best is None or len(name) > len(best)):
            best = name
    return trials[best] if best else None


def _set(item, key, value):
    if isinstance(item, dict):
        item[key] = value
    else:
        setattr(item, key, value)


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

@dc.dataclass
class LogGroup(object):
    """The samples destined for one `EvalLog`, and the identity that scopes it.

    `benchmark` and `view` are the grouping key -- `eval.task` and the model
    axis respectively. Two cases from different benchmarks share a run and a
    console report, but never a log.
    """
    benchmark : str = ""
    view : str = ""
    model : str = ""
    samples : List[Any] = dc.field(default_factory=list)

    @property
    def key(self) -> Tuple[str, str]:
        return (self.benchmark, self.view)


def group_samples(output, trials=None) -> List[LogGroup]:
    """Partition the reachable `std.EvalSample` items by (benchmark, view).

    Items that are not eval samples are ignored rather than rejected: a root
    may legitimately mix graded cases with ordinary tests, and those flow to
    the inherited test report instead. `trials` (trial node name -> Trial)
    supplies each sample's benchmark and view; a sample from no known trial
    falls in the ("", "") group.
    """
    groups : Dict[Tuple[str, str], LogGroup] = {}
    seen = set()
    for item in output or []:
        if not is_sample(item) or id(item) in seen:
            continue
        seen.add(id(item))
        tr = trial_for(item, trials)
        key = (tr.benchmark, tr.view) if tr is not None else ("", "")
        g = groups.get(key)
        if g is None:
            g = groups[key] = LogGroup(benchmark=key[0], view=key[1])
        g.samples.append(item)
    for g in groups.values():
        g.samples.sort(key=lambda s: (str(_get(s, "id") or ""), int(_get(s, "epoch") or 1)))
    return list(groups.values())


def resolve_model(group : LogGroup) -> str:
    """The model identity for a group's `eval.model` field.

    Read off the samples' `model_usage` keys rather than off the view name: a
    view is a harness variant, which may or may not correspond to one model,
    and a log that claims a model it did not use is worse than one that says
    nothing. A group whose samples disagree is a project error -- an
    `EvalLog` cannot span models -- and is reported as such. A group with no
    usage at all is `none`, Inspect's own spelling for "no model".
    """
    models = []
    for s in group.samples:
        for m in (_get(s, "model_usage") or {}):
            if m not in models:
                models.append(m)
    if len(models) > 1:
        raise LogWriteError(
            "eval log %s%s spans several models (%s); an EvalLog covers one. "
            "Split the cases into views by model." % (
                group.benchmark or "(no benchmark)",
                " [view=%s]" % group.view if group.view else "",
                ", ".join(models)))
    group.model = models[0] if models else "none"
    return group.model


# ---------------------------------------------------------------------------
# Reduction of a replicated case
# ---------------------------------------------------------------------------

def _scorers(samples) -> List[str]:
    names = []
    for s in samples:
        for k in (_get(s, "scores") or {}):
            if k not in names:
                names.append(k)
    return names


def inspect_reducer(reducer : str, epochs : int) -> str:
    """Our reducer's name in Inspect's vocabulary."""
    if reducer == "pass_at_k":
        return "pass_at_%d" % epochs
    if reducer == "all":
        return "at_least_%d" % epochs
    return reducer


def reduce_case(ctxt, case : str, name : str, samples : List[Any],
                reducer : str, epochs : int):
    """One `std.EvalCase` over a case's trials: the case's verdict.

    The verdict is the reducer applied to the trials' own verdicts (1.0 for
    a passing trial, 0.0 otherwise), passing at 0.5 -- so `pass_at_k`/`max`
    pass when any trial passed, `all`/`min` when every one did, and
    `mean`/`median` on a majority. A trial that reported nothing (it was
    blocked or crashed) counts as a failed one. Each scorer's score is
    reduced the same way into `score_<name>`. The trials are referenced in
    `trials`, not held as children: a case is one leaf of the run record,
    whatever its epoch count.
    """
    from ..results import api as R
    from ..results.status import worst_of
    samples = sorted(samples, key=lambda s: int(_get(s, "epoch") or 1))
    first = samples[0]
    item = R.mk_result(ctxt, CASE_TYPE, name=name)
    _set(item, "task", _get(first, "task") or "")
    if _get(first, "rundir"):
        _set(item, "rundir", _get(first, "rundir"))
    _set(item, "testname", case)
    _set(item, "epochs", epochs)
    _set(item, "reducer", reducer)
    _set(item, "trials", [{
        "type": _get(s, "type"), "epoch": int(_get(s, "epoch") or 1), "status": _get(s, "status") or "",
        "task": _get(s, "task") or "", "rundir": _get(s, "rundir") or "",
        "score": score_value(s)} for s in samples])

    metrics = {}
    for sc in _scorers(samples):
        vals = [score_value(s, sc) for s in samples if sc in (_get(s, "scores") or {})]
        metrics["score_%s" % sc] = R.metric(reduce_scores(vals, reducer),
                                            better="higher", label=sc)
    verdicts = [1.0 if trial_passed(s) else 0.0 for s in samples]
    missing = max(0, epochs - len(samples))
    verdicts += [0.0] * missing
    npass = int(sum(verdicts))
    metrics["verdict"] = R.metric(reduce_scores(verdicts, reducer), better="higher",
                                  label="%s over %d trials" % (reducer, epochs))
    metrics["trials_passed"] = R.metric(npass, better="higher")
    _set(item, "metrics", metrics)
    _set(item, "checks", [R.eval_check(
        metrics, reducer, "verdict", ">=", 0.5,
        "%d/%d trials passed" % (npass, epochs))])

    statuses = [_get(s, "status") or "pass" for s in samples]
    if npass == 0 and statuses and all(st in ("error", "timeout") for st in statuses):
        _set(item, "status", worst_of(statuses))
    msg = "%d/%d trials passed (%s)" % (npass, epochs, reducer)
    if missing:
        msg += "; %d reported nothing" % missing
    _set(item, "msg", msg)
    R.finish(item)
    return item


def _substitute(item, swap):
    """`item` with every trial sample in its tree replaced per `swap`
    (id(sample) -> case result, or None to drop it). A node whose children
    changed is copied and re-rolled; an unchanged one is returned as is."""
    from ..results.rollup import rollup
    from ..results.summary import count_msg
    if id(item) in swap:
        return swap[id(item)]
    kids = list(_get(item, "children") or [])
    if not kids:
        return item
    new = []
    changed = False
    for k in kids:
        k2 = _substitute(k, swap)
        if k2 is not k:
            changed = True
        if k2 is not None and all(k2 is not n for n in new):
            new.append(k2)
    if not changed:
        return item
    item = item.model_copy() if hasattr(item, "model_copy") else dict(item)
    _set(item, "children", new)
    status, counts, metrics = rollup(new)
    _set(item, "status", status)
    _set(item, "passed", status == "pass")
    _set(item, "counts", counts)
    _set(item, "metrics", metrics)
    _set(item, "msg", count_msg(counts))
    if _has(item, "total"):
        _set(item, "total", counts.get("total", 0))
        _set(item, "failed", counts.get("fail", 0))
        _set(item, "errored", counts.get("error", 0) + counts.get("timeout", 0))
    return item


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _per_case(group : LogGroup, scorer : str, reducer : str) -> Dict[str, float]:
    by_id : Dict[str, List[float]] = {}
    for s in group.samples:
        if scorer in (_get(s, "scores") or {}):
            by_id.setdefault(str(_get(s, "id") or ""), []).append(score_value(s, scorer))
    return {k: reduce_scores(v, reducer) for k, v in by_id.items()}


def build_results(group : LogGroup, reducer : str, epochs : int = 1) -> Dict[str, Any]:
    """The `results` block: per-scorer metrics, reduced across epochs.

    Samples are keyed by (`id`, `epoch`), so a case's trials collapse to one
    score via `reduce_scores` before the metric is computed. This is the only
    place reduction happens -- the CTRF status and the console verdict read
    what this produced, so the three cannot disagree.
    """
    scores = []
    for sc in _scorers(group.samples):
        per = _per_case(group, sc, reducer)
        if not per:
            continue
        mean = sum(per.values()) / len(per)
        scores.append({
            "name": sc, "scorer": sc,
            "reducer": inspect_reducer(reducer, epochs),
            "scored_samples": len(per), "unscored_samples": 0, "params": {},
            "metrics": {"mean": {"name": "mean", "value": mean, "params": {}}},
        })
    done = [s for s in group.samples if not _get(s, "error")]
    return {"total_samples": len(group.samples),
            "completed_samples": len(done), "scores": scores}


def build_reductions(group : LogGroup, reducer : str, epochs : int) -> List[Dict[str, Any]]:
    """Inspect's `reductions`: each scorer's per-sample score after the
    epochs reducer."""
    out = []
    for sc in _scorers(group.samples):
        per = _per_case(group, sc, reducer)
        out.append({"scorer": sc, "reducer": inspect_reducer(reducer, epochs),
                    "samples": [{"value": v, "sample_id": k} for k, v in per.items()]})
    return out


def build_stats(group : LogGroup) -> Dict[str, Any]:
    """The `stats` block: `model_usage` summed across the group's samples,
    plus the run's wall-clock span. Token accounting is Inspect's vocabulary,
    so nothing is renamed on the way in."""
    usage : Dict[str, Dict[str, Any]] = {}
    for s in group.samples:
        for model, u in (_get(s, "model_usage") or {}).items():
            tot = usage.setdefault(model, {})
            for k, v in (u or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    tot[k] = tot.get(k, 0) + v
    for tot in usage.values():
        for k in ("input_tokens", "output_tokens", "total_tokens"):
            tot.setdefault(k, 0)
    starts = [_get(s, "started_at") for s in group.samples if _get(s, "started_at")]
    ends = [_get(s, "completed_at") for s in group.samples if _get(s, "completed_at")]
    now = _now()
    return {"started_at": min(starts) if starts else now,
            "completed_at": max(ends) if ends else now,
            "model_usage": usage}


def build_log(group : LogGroup, *, eval_set_id : str, reducer : str,
              epochs : int, run_id : str = "") -> Dict[str, Any]:
    """One complete `EvalLog` document.

    Header first (`version`, `status`, `eval`, `plan`, `results`, `stats`),
    then `samples`. Inspect separates these itself -- the header is defined as
    an `EvalLog` without the samples field, and `write_eval_log(header_only=)`
    exists precisely so a header can be written against samples that are
    already on disk. Building them separately here keeps the door open to
    streaming assembly if a run ever produces more samples than fit in memory.
    """
    model = group.model or resolve_model(group)
    task = group.benchmark or "eval"
    ids = []
    for s in group.samples:
        sid = str(_get(s, "id") or "")
        if sid not in ids:
            ids.append(sid)
    eval_id = hashlib.sha1(("%s|%s|%s" % (eval_set_id, task, group.view)).encode()).hexdigest()[:22]
    metadata = {"dfm_run_id": run_id or eval_set_id}
    if group.view:
        metadata["dfm_view"] = group.view
    log = {
        "version": INSPECT_LOG_VERSION,
        "status": "success",
        "eval": {
            "eval_id": eval_id,
            "run_id": run_id or eval_set_id,
            "eval_set_id": eval_set_id,
            "created": _now(),
            "task": task,
            "task_id": hashlib.sha1(task.encode()).hexdigest()[:22],
            "task_version": 0,
            "dataset": {"name": task, "samples": len(ids), "sample_ids": ids},
            "model": model,
            "config": {"epochs": epochs,
                       "epochs_reducer": [inspect_reducer(reducer, epochs)]},
            "metadata": metadata,
        },
        "plan": {"name": "plan", "steps": [], "config": {}},
        "results": build_results(group, reducer, epochs),
        "stats": build_stats(group),
    }
    if epochs > 1:
        log["reductions"] = build_reductions(group, reducer, epochs)
    log["samples"] = [sample_to_inspect(s, model=model) for s in group.samples]
    return log


def _safe(text : str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-") or "eval"


def log_name(log : Dict[str, Any]) -> str:
    """Inspect's own `{timestamp}_{task}_{id}.json` naming. `list_eval_logs()`
    lists a `.json` file only when its name starts with an ISO timestamp, so
    the shape is not cosmetic. The view, when there is one, is part of the
    task segment, which keeps one file per group."""
    ev = log.get("eval", {})
    created = str(ev.get("created") or _now())
    stamp = re.sub(r"\.\d+", "", created).replace(":", "-")
    task = _safe(ev.get("task") or "eval").replace("_", "-")
    view = (ev.get("metadata") or {}).get("dfm_view")
    if view:
        task += "-" + _safe(view).replace("_", "-")
    return "%s_%s_%s.json" % (stamp, task, ev.get("eval_id") or "0")


def write_log_dir(rundir : str, logs : List[Dict[str, Any]],
                  *, log_dir : str, log_format : str) -> List[str]:
    """Write the eval set and return the paths written.

    The directory *is* the eval set, so nothing else goes in it: anything
    extra would be picked up by `list_eval_logs()` and reported as a member.
    Logs a previous run left there are removed first, for the same reason.

    `log_format: eval` shells out to `inspect log convert --to eval` after
    writing the JSON. Missing CLI is an error rather than a silent fallback to
    JSON -- a caller who asked for `.eval` is feeding a tool that wants it.
    """
    if log_format not in ("json", "eval"):
        raise LogWriteError("unknown log_format '%s' (have: json, eval)" % log_format)
    if os.path.isabs(log_dir) or ".." in log_dir.split(os.sep):
        raise LogWriteError("log_dir '%s' must be relative to the root rundir, "
                            "inside it" % log_dir)
    inspect = shutil.which("inspect") if log_format == "eval" else None
    if log_format == "eval" and inspect is None:
        raise LogWriteError("log_format: eval needs the `inspect` CLI on PATH "
                            "(pip install inspect-ai), or use log_format: json")
    d = os.path.join(rundir, log_dir)
    try:
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            if f.endswith((".json", ".eval")):
                os.unlink(os.path.join(d, f))
        paths = []
        for log in logs:
            path = os.path.join(d, log_name(log))
            with open(path, "w") as fp:
                json.dump(log, fp, indent=2, default=str)
            paths.append(path)
    except OSError as e:
        raise LogWriteError("cannot write the eval set to %s: %s" % (d, e))
    if log_format == "eval":
        out = []
        for path in paths:
            r = subprocess.run([inspect, "log", "convert", "--to", "eval",
                                "--output-dir", d, path],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise LogWriteError("inspect log convert failed for %s: %s" % (
                    path, (r.stderr or r.stdout).strip()))
            os.unlink(path)
            out.append(path[:-len(".json")] + ".eval")
        paths = out
    return paths


# ---------------------------------------------------------------------------
# The root's run body
# ---------------------------------------------------------------------------

def _run_id(ctxt) -> str:
    rid = getattr(getattr(ctxt, "ctxt", None), "run_id", "") or ""
    return rid or os.environ.get("DFM_RUN_ID", "")


async def EvalRunnerRun(ctxt, input):
    """`run:` body of `std.EvalRunner`.

    Stamps each sample with the identity of the trial that produced it
    (`epoch`, and `id` when the grader left it empty), reduces each
    replicated case to a `std.EvalCase`, emits the `std.TestRunResult` over
    the cases, and writes the eval set under `log_dir`. The inputs pass
    through as for `std.TestRunner`.
    """
    from dv_flow.mgr import TaskDataResult, TaskMarker
    from ..results import api as R
    from .eval_select import check_epochs
    from .result_collect import collect

    p = input.params
    reducer = str(getattr(p, "epochs_reducer", "mean") or "mean")
    markers = []
    try:
        epochs = check_epochs(getattr(p, "epochs", 1))
        if reducer not in REDUCERS:
            raise ReducerError("unknown epochs reducer '%s' (have: %s)" % (
                reducer, ", ".join(sorted(REDUCERS))))
    except Exception as e:
        return TaskDataResult(status=1, markers=[
            TaskMarker(msg=str(e), severity="error")])

    node = getattr(ctxt, "_task", None)
    trials = getattr(node, "eval_trials", None) or {}
    inputs = list(input.inputs)
    samples = [it for it in inputs if is_sample(it)]

    by_case : Dict[str, List[Any]] = {}
    names : Dict[str, str] = {}
    for s in samples:
        tr = trial_for(s, trials)
        if tr is None:
            continue
        _set(s, "epoch", tr.epoch)
        if not _get(s, "id"):
            _set(s, "id", tr.sample_id)
        if epochs > 1:
            by_case.setdefault(tr.case, []).append(s)
            names[tr.case] = tr.name

    if by_case:
        swap = {}
        for case, ss in by_case.items():
            c = reduce_case(ctxt, case, names[case], ss, reducer, epochs)
            swap[id(ss[0])] = c
            for s in ss[1:]:
                swap[id(s)] = None
        rewritten = []
        for it in inputs:
            it2 = _substitute(it, swap)
            if it2 is not None:
                rewritten.append(it2)
        inputs = rewritten

    root = collect(ctxt, inputs, type="std.TestRunResult", empty_ok=False)
    output = [root] if root is not None else []

    groups = group_samples(samples, trials)
    if groups:
        eval_set_id = str(getattr(p, "eval_set_id", "") or "") or _run_id(ctxt) \
            or os.path.basename(input.rundir)
        log_dir = str(getattr(p, "log_dir", "logs") or "logs")
        try:
            logs = [build_log(g, eval_set_id=eval_set_id, reducer=reducer,
                              epochs=epochs, run_id=_run_id(ctxt)) for g in groups]
            paths = write_log_dir(input.rundir, logs, log_dir=log_dir,
                                  log_format=str(getattr(p, "log_format", "json") or "json"))
        except (LogWriteError, ReducerError) as e:
            markers.append(TaskMarker(msg=str(e), severity="error"))
            if root is not None:
                # The verdict says the eval set is missing, not just the task.
                checks = list(_get(root, "checks") or [])
                checks.append(R.check("eval_log", "error", msg=str(e)))
                _set(root, "checks", checks)
                _set(root, "msg", "eval log not written: %s" % e)
                R.finish(root)
            return TaskDataResult(status=1, markers=markers, output=output)
        if root is not None:
            arts = list(_get(root, "artifacts") or [])
            for path in paths:
                arts.append(R.artifact(ctxt, path, "report", filetype="inspectEvalLog",
                                       label="eval log"))
            _set(root, "artifacts", arts)
        _log.info("eval set %s: %d log(s) in %s", eval_set_id, len(paths),
                  os.path.join(input.rundir, log_dir))
    return TaskDataResult(output=output)


# ---------------------------------------------------------------------------
# The summary hook
# ---------------------------------------------------------------------------

def eval_summary(ctxt):
    """`summary:` callable for `std.EvalRunner`.

    Defers to the inherited test report for the console output and appends a
    line naming the log directory. The eval set itself was written by the
    root's run body; nothing is recomputed here, because a summary must never
    change the verdict.
    """
    from .test_summary import test_summary
    report = test_summary(ctxt)
    logs = []
    for it in list(getattr(ctxt, "output", None) or []):
        for a in _get(it, "artifacts") or []:
            if _get(a, "filetype") == "inspectEvalLog":
                for f in _get(a, "files") or []:
                    logs.append(os.path.join(_get(a, "basedir") or "", f))
    if not logs:
        return report
    from rich.console import Group
    from rich.text import Text
    line = Text("Eval logs: %s" % os.path.dirname(logs[0]))
    if len(logs) > 1:
        line.append(" (%d logs)" % len(logs))
    return Group(report, line) if report is not None else line
