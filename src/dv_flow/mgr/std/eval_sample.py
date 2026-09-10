#****************************************************************************
#* eval_sample.py
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
"""Per-trial results: writing an Inspect `EvalSample`, and reducing scores
across epochs.

One trial writes one sample into its own rundir. That is not a stylistic
choice -- it is what makes the trial an ordinary DFM task: no shared file, no
append lock, no coordination between the workers a Slurm run spreads them
across, and a re-run of a single trial rewrites exactly one file, so caching
works per-trial rather than per-suite.

The samples become a log only at the root, where something finally sees all of
them (`eval_log`).

Nothing here imports `inspect_ai`. The sample is written against the published
schema, which is JSON and stable; taking the library would pull model-provider
dependencies into every worker for the sake of a serializer.
"""

import dataclasses as dc
import json
import logging
import os
from typing import Any, Dict, List, Optional

_log = logging.getLogger("eval_sample")

# The filename a trial writes into its own rundir. Fixed rather than derived:
# the assembler finds samples through dataflow, not by globbing, so the name
# only has to be predictable to a human reading a rundir.
SAMPLE_FILE = "sample.json"


class ReducerError(Exception):
    """An unknown reducer was named. Raised rather than defaulting to `mean`:
    silently reducing a `pass_at_k` eval by averaging reports a number that
    looks like a result and is not the one that was asked for."""


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_sample(rundir : str, sample : Any) -> str:
    """Serialize `sample` to `<rundir>/sample.json` and return the path.

    `sample` is a `std.EvalSample` data item. Fields the grader left unset are
    written as their schema defaults rather than omitted, so a consumer never
    has to distinguish "absent" from "empty" -- the same reason the test
    report reads verdicts structurally.
    """
    raise NotImplementedError


def sample_to_inspect(sample : Any, *, events : Optional[List[Any]] = None) -> Dict[str, Any]:
    """A `std.EvalSample` item -> an Inspect `EvalSample` dict.

    Mostly a rename-free copy: the type's fields were chosen to match, so this
    exists to drop the two fields Inspect has no place for (`passed`,
    `status`, which the inherited test report reads) and to inline `events`
    when the caller has read the trajectory file.

    `passed`/`status` are not lost -- they are recoverable from `scores`, and
    the reduction that produces the case verdict uses `scores`, so the two
    representations cannot drift.
    """
    raise NotImplementedError


def read_trajectory(rundir : str, path : str) -> List[Dict[str, Any]]:
    """Load a Trajectory-v1 transcript from `<rundir>/<path>`.

    Returns the records as-is: a leading `role: "meta"` record carrying
    `source`/`cwd`/`git_branch`/`model`, then `user`/`reasoning`/`assistant`/
    `tool` records. Inspect's `events` is a different vocabulary; the
    conversion is deliberately not done here, because a trajectory is worth
    keeping in the form the harness produced it even when no log is assembled.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Reduction
# ---------------------------------------------------------------------------
#
# A case that ran `epochs` times has `epochs` scores and needs one verdict.
# Which reduction is correct is a property of the benchmark, not of the
# runner, so it is a parameter -- but it must be applied in exactly one place,
# or the console report, the CTRF status, and the log's `results` block will
# each answer the question differently.
#
# These operate on floats in [0.0, 1.0]. A boolean verdict is 1.0/0.0, which
# is what makes `pass_at_k` and `mean` the same function over different data.

def _mean(values : List[float]) -> float:
    return sum(values) / len(values)


def _median(values : List[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _pass_at_k(values : List[float]) -> float:
    """1.0 if any trial passed. k is the epoch count, so this is pass@k for
    whatever k the run used -- naming it in the reducer as well would let the
    two disagree."""
    return 1.0 if any(v > 0.0 for v in values) else 0.0


def _all(values : List[float]) -> float:
    return 1.0 if all(v > 0.0 for v in values) else 0.0


REDUCERS = {
    "mean":      _mean,
    "median":    _median,
    "max":       max,
    "min":       min,
    "pass_at_k": _pass_at_k,
    "all":       _all,
}


def reduce_scores(values : List[float], reducer : str) -> float:
    """Combine per-trial scores into a case score.

    An empty `values` is a caller error: a case with no trials should not
    reach reduction at all, and returning 0.0 for it would report a failure
    the run never observed.
    """
    if not values:
        raise ReducerError("cannot reduce an empty score set")
    fn = REDUCERS.get(reducer)
    if fn is None:
        raise ReducerError("unknown epochs reducer '%s' (have: %s)" % (
            reducer, ", ".join(sorted(REDUCERS))))
    return float(fn(values))


def score_value(sample : Any, scorer : Optional[str] = None) -> float:
    """The numeric score of one trial.

    Prefers `scores[scorer].value`, falling back to the single scorer when
    there is exactly one, and to `passed` when a grader recorded a verdict
    without a score. The fallback chain is what lets a boolean grader and a
    continuous one feed the same root.
    """
    raise NotImplementedError
