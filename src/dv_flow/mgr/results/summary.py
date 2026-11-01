#****************************************************************************
#* summary.py -- the summary block of results.json
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
#*
#****************************************************************************
"""The ``summary`` block of a run record, computed the same way for every
domain:

* ``status``, ``msg`` and ``metrics`` come from the root node (``msg`` is a
  count line when the root has none; ``walltime_s`` is the run's).
* ``counts`` tallies the statuses of the leaf nodes.
* ``failures`` lists every non-passing leaf, every non-passing
  ``std.TaskResult``, and every non-passing parent that no non-passing child
  explains (it failed on its own checks), with its failing checks, the first
  log location and the first waveform.
"""
import os
from typing import Optional

from .model import FailureEntry, Metric, ResultNode, Summary
from .rollup import TASKS_GROUP, leaf_counts, is_leaf
from .status import is_ok


def _artifact_path(a, i=0):
    if not a.files:
        return None
    f = a.files[i]
    return os.path.join(a.basedir, f) if a.basedir and not os.path.isabs(f) else f


def first_artifact(node: ResultNode, role: str) -> Optional[str]:
    for a in node.artifacts:
        if a.role == role:
            p = _artifact_path(a)
            if p:
                return p
    return None


def log_ref(node: ResultNode):
    """``{path, line}`` of the log to open: the first ``log`` artifact, at
    the first diagnostic that points into it."""
    log = first_artifact(node, "log")
    line = None
    for d in node.diagnostics:
        if d.loc is None:
            continue
        if log is None and d.loc.path:
            return {"path": d.loc.path, "line": d.loc.line}
        if d.loc.path == log or (not d.loc.path and d.loc.line is not None):
            line = d.loc.line
            break
    if log is None:
        return None
    return {"path": log, "line": line}


def _walk(node, path):
    yield node, path
    for c in node.children:
        yield from _walk(c, path + "/" + (c.name or "?"))


def _own(node):
    return getattr(node, "own_status", None) or node.status


def failures(root: ResultNode):
    ret = []
    for node, path in _walk(root, root.name or "<root>"):
        # A root raised to `error` only because of the `_tasks` it gained
        # keeps its own status (`own_status`); the tasks are listed instead.
        own = _own(node)
        if is_ok(own):
            continue
        task_result = "std.TaskResult" in node.types
        # A parent is listed when it fails on its own (a synth run's timing
        # check with passing stages); one that fails because a child does is
        # explained by that child.
        explained = any(not is_ok(_own(c)) for c in node.children
                        if c.name != TASKS_GROUP)
        if not (is_leaf(node) or task_result or not explained):
            continue
        ent = {"path": path, "status": own, "msg": node.msg,
               "type": node.type}
        if node.task:
            ent["task"] = node.task
        ent["checks"] = [c for c in node.checks if c.status in ("fail", "error")]
        lr = log_ref(node)
        if lr is not None:
            ent["log"] = lr
        w = first_artifact(node, "waves")
        if w:
            ent["waves"] = w
        ret.append(FailureEntry.model_validate(ent))
    return ret


def count_msg(counts, failures=()) -> str:
    """"all 6 passed" / "1 of 6 failed, 1 not run". A parent that failed on
    its own checks is a failure the leaf counts don't show, so the failed
    number is never less than the failures listed."""
    total = counts.get("total", 0)
    bad = sum(counts.get(k, 0) for k in ("fail", "error", "timeout"))
    bad = max(bad, sum(1 for f in failures if f.status in ("fail", "error", "timeout")))
    notrun = counts.get("notrun", 0)
    if total == 0:
        return "no results"
    if bad == 0 and notrun == 0:
        return "all %d passed" % total if total > 1 else "passed"
    parts = []
    if bad:
        parts.append("%d of %d failed" % (bad, total))
    if notrun:
        parts.append("%d not run" % notrun)
    return ", ".join(parts)


def compute_summary(root: ResultNode, walltime_s: Optional[float] = None) -> Summary:
    counts = leaf_counts([root])
    metrics = dict(root.metrics)
    if walltime_s is not None:
        metrics["walltime_s"] = Metric(value=round(walltime_s, 3), unit="s", better="lower")
    fl = failures(root)
    return Summary(status=root.status, msg=root.msg or count_msg(counts, fl),
                   counts=counts, metrics=metrics, failures=fl)
