#****************************************************************************
#* eval_select.py
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
"""Selection plus trials: the elaborator behind `std.EvalRunner`.

Selection itself is not reimplemented. `TestSelect` already prunes the
need-set, rebuilds narrowed suite matrices, and rejects a selection that
matches nothing; a `std.Eval` is a `std.Test`, so all of that applies
unchanged. This wraps it and adds one thing: each surviving case is replicated
`epochs` times.

Replication is done at graph build, as distinct nodes, rather than as a loop
inside one node. That is the reason to run a benchmark on DFM at all -- trials
are the parallelism, and node-per-trial gets them distributed across the
configured backend, cached individually, and retried individually. The cost is
that a case's score exists only at the root, where the reduction happens.
"""

import dataclasses as dc
import logging
from typing import Any, Dict, List, Optional

from .test_select import (Selection, SelectionError, TestPlan, TestSelect,
                          run_nodes, test_tag)

_log = logging.getLogger("eval_select")

EVAL_TAG = "std.Eval"


class EpochError(Exception):
    """`epochs` was not a positive integer. Raised rather than clamped: zero
    trials would produce an empty log and report success for a benchmark that
    never ran."""


def epoch_name(name : str, epoch : int, epochs : int) -> str:
    """The node name for one trial of a case.

    A single-epoch run keeps the bare name, so the common case reads the way a
    test run does and rundir paths do not churn when trials are introduced.
    Beyond that, trials are suffixed `.e<N>` -- 1-based, matching
    `EvalSample.epoch`, so a rundir maps to a log entry by inspection.
    """
    return name if epochs <= 1 else "%s.e%d" % (name, epoch)


def check_epochs(value) -> int:
    try:
        epochs = int(value)
    except (TypeError, ValueError):
        raise EpochError("epochs must be a positive integer, not %r" % (value,))
    if epochs < 1 or str(value).strip() != str(epochs):
        raise EpochError("epochs must be a positive integer, not %r" % (value,))
    return epochs


def eval_tag(task) -> Optional[Any]:
    """The `std.Eval` tag's values for `task`, or None. Structural for the
    same reason `test_tag` is: a tag instance keeps no `uses` link, so a
    project-derived tag is recognized by the field only `std.Eval` adds."""
    for tag in getattr(task, "tags", None) or []:
        values = getattr(tag, "paramT", None)
        if values is None:
            continue
        if getattr(tag, "name", None) == EVAL_TAG or hasattr(values, "sample_id"):
            return values
    return None


def _never_uptodate(node) -> None:
    """Mark a trial's own nodes -- the node and its body, not its needs --
    as never up-to-date (no uptodate check, no cache)."""
    stack = [node]
    while stack:
        n = stack.pop()
        if hasattr(n, "uptodate"):
            n.uptodate = False
        stack.extend(getattr(n, "tasks", None) or [])


def replicate(ctxt, task, epochs : int) -> List[Any]:
    """Build `epochs` independent nodes for one selected case.

    Each carries its own `epoch`, which reaches the grader and lands in the
    sample. Nothing else differs between them -- and in particular no seed is
    injected: a benchmark trial is meant to sample the agent's real behavior,
    and pinning it to a seed would measure something else.

    The epoch reaches the case as its `epoch` parameter when it declares one;
    either way the root fills `EvalSample.epoch` from the trial that produced
    the sample. Trials are built under distinct names, so the builder's node
    memo cannot deduplicate them, and they are never up-to-date (see
    `EvalSelect`).
    """
    params = ctxt.mkParams(task)
    has_epoch = params is not None and hasattr(params, "epoch")
    nodes = []
    for e in range(1, epochs + 1):
        kw = {"epoch": e} if has_epoch else {}
        node = ctxt.mkTaskNode(task, name=epoch_name(task.name, e, epochs), **kw)
        _never_uptodate(node)
        nodes.append(node)
    return nodes


@dc.dataclass
class Trial(object):
    """One trial node's identity, for the root to stamp onto its sample."""
    case : str                  # the case's test path, dotted
    name : str                  # the case's own path segment
    epoch : int
    benchmark : str = ""
    sample_id : str = ""
    view : str = ""


@dc.dataclass
class EvalPlan(TestPlan):
    """`TestPlan`, plus each replicated case's trial nodes. A replicated case
    is not in the graph under its own name, so `runs()` reports its trials."""
    replicas : Dict[str, List[Any]] = dc.field(default_factory=dict)

    def runs(self, root_node):
        base = TestPlan.runs(self, root_node)
        kept = [t for k, t in self.tree.tests.items() if self.res.kept.get(k)]
        return [(path, nodes or self.replicas.get(t.task.name, []))
                for (path, nodes), t in zip(base, kept)]


def _swap(root, original, replicas) -> None:
    """Replace every need edge on `original` in the graph under `root` with
    edges on `replicas`."""
    seen = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        needs = getattr(node, "needs", None)
        if needs:
            new = []
            for entry in needs:
                n, block = entry if isinstance(entry, tuple) else (entry, False)
                if n is original:
                    new.extend((r, block) for r in replicas)
                else:
                    new.append(entry)
                    stack.append(n)
            needs[:] = new
        stack.extend(getattr(node, "tasks", None) or [])


def trials_of(plan, root_node, epochs : int) -> Dict[str, Trial]:
    """Trial node name -> `Trial`, for every selected eval case."""
    from .test_select import format_path
    replicas = getattr(plan, "replicas", {}) or {}
    out : Dict[str, Trial] = {}
    nodes = run_nodes(plan.tree, plan.res, root_node, plan.test_key)
    for key, t in plan.tree.tests.items():
        if not plan.res.kept.get(key):
            continue
        tag = eval_tag(t.task)
        if tag is None:
            continue
        found = [(view, ns) for (k, view), ns in nodes.items() if k == key]
        if not found and t.task.name in replicas:
            found = [(t.view or None, replicas[t.task.name])]
        for view, ns in found:
            for i, n in enumerate(ns):
                out[n.name] = Trial(
                    case=format_path(t.path), name=t.name,
                    epoch=(i + 1) if t.task.name in replicas else 1,
                    benchmark=str(getattr(tag, "benchmark", "") or ""),
                    sample_id=str(getattr(tag, "sample_id", "") or "") or
                    (key[1] if key[1] is not None else t.name),
                    view=str(view or ""))
    return out


def EvalSelect(ctxt, task, name):
    """`elaborate:` entry point for `std.EvalRunner`.

    Delegates to `TestSelect` for the selected interior, then replicates each
    selected eval case `epochs` times, wiring the replicas in place of the
    original. Cases carrying no `std.Eval` tag -- an ordinary test, an image,
    a helper -- are left alone: a root may mix graded and ungraded work, and
    replicating a build step would be nonsense.

    An eval case is never up-to-date. An agent invocation is nondeterministic,
    so a cached result is a different sample than the one the trial was asked
    to draw; serving four cached copies of trial 1 would make `pass_at_k`
    report the reliability of the cache.

    A case that is a cell of a matrix suite cannot be replicated yet
    (`epochs > 1` with one is an error rather than a silent single trial).
    """
    params = ctxt.mkParams(task)
    epochs = check_epochs(getattr(params, "epochs", 1))

    node = TestSelect(ctxt, task, name)
    plan = getattr(node, "test_plan", None)
    if plan is None:            # --build-only: nothing runs
        return node

    replicas : Dict[str, List[Any]] = {}
    built = run_nodes(plan.tree, plan.res, node, plan.test_key)
    for key, t in plan.tree.tests.items():
        if not plan.res.kept.get(key) or eval_tag(t.task) is None:
            continue
        cases = [ns for (k, _v), ns in built.items() if k == key]
        cells = key[1] is not None or t.task.name in plan.tree.matrix_tests
        if epochs > 1 and cells:
            raise SelectionError(
                "epochs=%d: eval case %s is a matrix cell, and matrix cells "
                "cannot be replicated yet. Run it with epochs=1, or declare "
                "the case as its own task." % (epochs, ".".join(t.path)))
        for ns in cases:
            for n in ns:
                _never_uptodate(n)
        if epochs == 1 or t.task.name in replicas or not cases:
            continue
        reps = replicate(ctxt, t.task, epochs)
        for n in cases[0]:
            _swap(node, n, reps)
        replicas[t.task.name] = reps

    node.test_plan = EvalPlan(tree=plan.tree, res=plan.res,
                              test_key=plan.test_key, replicas=replicas)
    node.eval_trials = trials_of(node.test_plan, node, epochs)
    _log.debug("eval trials: %s", sorted(node.eval_trials))
    return node
