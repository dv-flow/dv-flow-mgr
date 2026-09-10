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
dataflow, at the root, once everything has run. This groups them into Inspect
`EvalLog` documents and writes the log directory.

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
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from .eval_sample import reduce_scores, score_value

_log = logging.getLogger("eval_log")

# Bumped when the assembled layout changes incompatibly. Tracks Inspect's
# `EvalLog.version`, which is what a consumer actually validates against.
INSPECT_LOG_VERSION = 2


class LogWriteError(Exception):
    """The eval set could not be written. Raised rather than warned: a
    benchmark run whose results went nowhere has produced nothing, and
    reporting success for it is worse than failing."""


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


def group_samples(output) -> List[LogGroup]:
    """Partition the reachable `std.EvalSample` items by (benchmark, view).

    Items that are not eval samples are ignored rather than rejected: a root
    may legitimately mix graded cases with ordinary tests, and those flow to
    the inherited test report instead.
    """
    raise NotImplementedError


def resolve_model(group : LogGroup) -> str:
    """The model identity for a group's `eval.model` field.

    Read off the samples' `model_usage` keys rather than off the view name: a
    view is a harness variant, which may or may not correspond to one model,
    and a log that claims a model it did not use is worse than one that says
    nothing. A group whose samples disagree is a project error -- an
    `EvalLog` cannot span models -- and is reported as such.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_results(group : LogGroup, reducer : str) -> Dict[str, Any]:
    """The `results` block: per-scorer metrics, reduced across epochs.

    Samples are keyed by (`id`, `epoch`), so a case's trials collapse to one
    score via `reduce_scores` before the metric is computed. This is the only
    place reduction happens -- the CTRF status and the console verdict read
    what this produced, so the three cannot disagree.
    """
    raise NotImplementedError


def build_stats(group : LogGroup) -> Dict[str, Any]:
    """The `stats` block: `model_usage` summed across the group's samples,
    plus the run's wall-clock span. Token accounting is Inspect's vocabulary,
    so nothing is renamed on the way in."""
    raise NotImplementedError


def build_log(group : LogGroup, *, eval_set_id : str, reducer : str,
              epochs : int) -> Dict[str, Any]:
    """One complete `EvalLog` document.

    Header first (`version`, `status`, `eval`, `plan`, `results`, `stats`),
    then `samples`. Inspect separates these itself -- the header is defined as
    an `EvalLog` without the samples field, and `write_eval_log(header_only=)`
    exists precisely so a header can be written against samples that are
    already on disk. Building them separately here keeps the door open to
    streaming assembly if a run ever produces more samples than fit in memory.
    """
    raise NotImplementedError


def write_log_dir(rundir : str, logs : List[Dict[str, Any]],
                  *, log_dir : str, log_format : str) -> List[str]:
    """Write the eval set and return the paths written.

    The directory *is* the eval set, so nothing else goes in it: anything
    extra would be picked up by `list_eval_logs()` and reported as a member.

    `log_format: eval` shells out to `inspect log convert --to eval` after
    writing the JSON. Missing CLI is an error rather than a silent fallback to
    JSON -- a caller who asked for `.eval` is feeding a tool that wants it.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# The summary hook
# ---------------------------------------------------------------------------

def eval_summary(ctxt):
    """`summary:` callable for `std.EvalRunner`.

    Writes the eval set, then defers to the inherited test report for the
    console output and appends a line naming the log directory. The verdict
    itself is not recomputed here: the reduced scores this assembled are what
    the report already read, and a summary must never change the verdict.
    """
    raise NotImplementedError
