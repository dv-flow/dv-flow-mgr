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

import logging
from typing import Any, List, Optional

from .test_select import Selection, TestSelect, plan_need

_log = logging.getLogger("eval_select")


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


def replicate(ctxt, node, epochs : int) -> List[Any]:
    """Build `epochs` independent nodes for one selected case.

    Each carries its own `epoch`, which reaches the grader and lands in the
    sample. Nothing else differs between them -- and in particular no seed is
    injected: a benchmark trial is meant to sample the agent's real behavior,
    and pinning it to a seed would measure something else.

    Trials must not be deduplicated by the builder's node memo, and must not
    be served from cache across epochs; see `EvalSelect` for why the eval case
    task is `uptodate: false`.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError
