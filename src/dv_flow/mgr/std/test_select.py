#****************************************************************************
#* test_select.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
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
"""Graph-build test selection: the elaborator behind `std.TestRunner`.

A test-running root receives the available cases and suites as `needs:`. This
prunes that need-set from a command-line selection **at graph build**, so a
deselected test is *never built* -- not built-and-skipped. Everything reachable
only through a pruned edge drops out too, which is why deselecting a DUT view
also skips compiling that view's simulation image.

That is the point of doing it here rather than with `iff:`, which was the
earlier design: `iff: false` still constructs a stub node, and its upstream
image still gets built.

Two granularities, because a project has both:

* **a case** -- a task carrying a `std.Test` tag, kept or dropped whole;
* **a suite** -- a matrix task whose cells are cases. The suite is rebuilt as a
  locally-derived variant whose matrix axis holds only the selected cells, so
  unselected cells are never generated.

Needs the elaborator does not recognize as tests -- an image, a flags item, a
helper -- are **always kept**. Selection must never break the build.
"""

import dataclasses as dc
import logging
from typing import Any, Dict, List, Optional

from ..task import Strategy

_log = logging.getLogger("test_select")

TEST_TAG = "std.Test"


class SelectionError(Exception):
    """A selection that cannot be honored. Raised rather than reported-and-
    continued: every failure mode here ends in a run that tests less than the
    user asked for, and the worst of them is a green run that tested nothing."""


# ---------------------------------------------------------------------------
# Selection spec
# ---------------------------------------------------------------------------

@dc.dataclass
class Selection(object):
    """What the user asked to run. An empty dimension means "all of it"."""

    tests : List[str] = dc.field(default_factory=list)
    views : List[str] = dc.field(default_factory=list)
    test_key : str = "name"
    view_axis : str = "view"

    @classmethod
    def from_params(cls, params) -> 'Selection':
        return cls(
            tests=_as_list(getattr(params, "tests", None)),
            views=_as_list(getattr(params, "views", None)),
            test_key=getattr(params, "test_key", None) or "name",
            view_axis=getattr(params, "view_axis", None) or "view")

    @property
    def active(self) -> bool:
        return bool(self.tests or self.views)

    def wants_test(self, case) -> bool:
        return not self.tests or case in self.tests

    def wants_view(self, view) -> bool:
        return not self.views or view in self.views


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Defensive: the ladder coerces a `-D a,b` into a list before we see it.
        return [v for v in (s.strip() for s in value.split(",")) if v]
    return [str(v) for v in value]


# ---------------------------------------------------------------------------
# Reading a std.Test tag off a task
# ---------------------------------------------------------------------------

def test_tag(task) -> Optional[Any]:
    """The `std.Test` tag's resolved values for `task`, or None.

    A tag instance materializes its values into `paramT`, so the fields are read
    as ordinary attributes. Note the instance does *not* keep a `uses` link back
    to its declared type (`_instantiateTag` builds a fresh `Type`), so an is-a
    test is impossible -- hence the structural fallback: any tag exposing a
    `case` field is treated as a test tag, which lets a project derive its own
    tag type from `std.Test`.
    """
    for tag in getattr(task, "tags", None) or []:
        values = getattr(tag, "paramT", None)
        if values is None:
            continue
        if getattr(tag, "name", None) == TEST_TAG or hasattr(values, "case"):
            return values
    return None


def _matrix_of(task):
    """The task's matrix axes if it is a matrix strategy task, else None."""
    strategy = getattr(task, "strategy", None)
    if strategy is None:
        return None
    matrix = getattr(strategy, "matrix", None)
    return matrix if matrix else None


def _case_axis(matrix, test_key):
    """The axis whose cells are maps carrying `test_key` -- the case axis."""
    for axis, values in matrix.items():
        if isinstance(values, list) and any(
                isinstance(v, dict) and test_key in v for v in values):
            return axis
    return None


# ---------------------------------------------------------------------------
# Classification + filtering
# ---------------------------------------------------------------------------

@dc.dataclass
class Plan(object):
    """The decision for one declared need."""
    task : Any
    is_test : bool = False
    keep : bool = True
    variant : Any = None          # a filtered matrix variant, when rebuilt
    cases : List[str] = dc.field(default_factory=list)   # case keys it offers
    views : List[str] = dc.field(default_factory=list)   # view keys it offers
    # True when this need's view axis is an unexpanded expression, so its
    # members are NOT knowable here. Validation must then not claim a view is
    # unavailable -- rejecting a working flow is worse than missing a typo.
    views_open : bool = False


def plan_need(need, sel : Selection, expand=None) -> Plan:
    """Decide what to do with one declared need.

    `expand`, when given, evaluates a `${{ }}` expression -- used to resolve a
    matrix axis that is still an expression so its members can be validated
    rather than treated as unknowable.
    """
    matrix = _matrix_of(need)
    if matrix is not None:
        return _plan_matrix(need, matrix, sel, expand)

    values = test_tag(need)
    if values is not None:
        case = getattr(values, "case", "") or ""
        view = getattr(values, "view", "") or ""
        return Plan(
            task=need, is_test=True,
            keep=(sel.wants_test(case) if case else not sel.tests)
                 and (sel.wants_view(view) if view else not sel.views),
            cases=[case] if case else [],
            views=[view] if view else [])

    # Not recognizable as a test: infrastructure. Always kept.
    return Plan(task=need, is_test=False, keep=True)


def _plan_matrix(need, matrix, sel : Selection, expand=None) -> Plan:
    """Filter a suite's matrix axes to the selection.

    Returns a Plan whose `variant` is a locally-derived copy of the task with
    narrowed axes. If an axis filters down to nothing the whole suite is
    dropped -- an empty matrix would otherwise build a suite that runs nothing.
    """
    case_axis = _case_axis(matrix, sel.test_key)
    offered_cases, offered_views = [], []
    narrowed : Dict[str, Any] = dict(matrix)
    changed = False

    if case_axis is not None:
        cells = matrix[case_axis]
        offered_cases = [c[sel.test_key] for c in cells
                         if isinstance(c, dict) and sel.test_key in c]
        if sel.tests:
            kept = [c for c in cells
                    if not isinstance(c, dict)
                    or sel.wants_test(c.get(sel.test_key))]
            if len(kept) != len(cells):
                narrowed[case_axis] = kept
                changed = True
            if not kept:
                return Plan(task=need, is_test=True, keep=False,
                            cases=offered_cases)

    views_open = False
    view_axis = sel.view_axis if sel.view_axis in matrix else None
    if view_axis is not None:
        values = matrix[view_axis]
        if not isinstance(values, list) and expand is not None:
            # The axis is an expression (`image: "${{ images }}"`). Resolve it
            # so its members are validatable; without this a mistyped view is
            # bound literally and fails much later, deep in the flow, with an
            # error that names neither the view nor the flag that set it.
            resolved = expand(values)
            if isinstance(resolved, list):
                values = resolved
        if not isinstance(values, list):
            views_open = True
        if isinstance(values, list):
            offered_views = [str(v) for v in values]
            if sel.views:
                kept = [v for v in values if sel.wants_view(str(v))]
                if len(kept) != len(values):
                    narrowed[view_axis] = kept
                    changed = True
                if not kept:
                    return Plan(task=need, is_test=True, keep=False,
                                cases=offered_cases, views=offered_views)
        elif sel.views:
            # The axis is an unexpanded expression (e.g. `"${{ images }}"`),
            # so its members are not knowable here. The user named the views
            # they want, so bind them literally; there is nothing to validate
            # against, which is why an expression axis cannot report an
            # unmatched view.
            narrowed[view_axis] = list(sel.views)
            changed = True

    variant = None
    if changed:
        variant = dc.replace(
            need, strategy=Strategy(matrix=narrowed), paramT=None)

    is_test = case_axis is not None or view_axis is not None
    return Plan(task=need, is_test=is_test, keep=True, variant=variant,
                cases=offered_cases, views=offered_views,
                views_open=views_open)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def check_selection(sel : Selection, plans : List[Plan]):
    """Reject a selection that would silently under-run.

    Both failure modes below end in a *green* run covering less than asked --
    the one outcome a test command must never produce quietly.
    """
    if not sel.active:
        return

    test_plans = [p for p in plans if p.is_test]
    if not test_plans:
        raise SelectionError(
            "a test selection was given, but none of this task's needs are "
            "recognizable as tests. Tag a case with `tags: [{std.Test: "
            "{case: <name>}}]`, or give a suite a matrix axis whose cells "
            "carry a '%s' field." % sel.test_key)

    offered = sorted({c for p in test_plans for c in p.cases if c})
    unmatched = [t for t in sel.tests if t not in offered] if offered else []
    if unmatched:
        raise SelectionError(
            "no test matches %s. Available: %s" % (
                ", ".join("'%s'" % u for u in unmatched),
                ", ".join(offered) if offered else "(none)"))

    # Only validate views when EVERY suite's view axis was knowable. A suite
    # whose axis is an expression (`image: "${{ images }}"`) contributes no
    # names, so an incomplete offered-set would reject a perfectly good view --
    # the false-positive failure mode that matters most here.
    offered_views = sorted({v for p in test_plans for v in p.views if v})
    views_known = offered_views and not any(p.views_open for p in test_plans)
    if views_known:
        unmatched_v = [v for v in sel.views if v not in offered_views]
        if unmatched_v:
            raise SelectionError(
                "no view matches %s. Available: %s" % (
                    ", ".join("'%s'" % u for u in unmatched_v),
                    ", ".join(offered_views)))

    if not any(p.keep for p in test_plans):
        raise SelectionError(
            "the selection matched no tests, so the run would report success "
            "without testing anything")


# ---------------------------------------------------------------------------
# The elaborator
# ---------------------------------------------------------------------------

def TestSelect(ctxt, task, name):
    """`elaborate:` entry point for `std.TestRunner`.

    Builds the standard interior with the deselected needs withheld, then wires
    back the selected ones -- rebuilding a suite as a narrowed-matrix variant
    where the selection reaches inside it.

    Suites are wired explicitly rather than left to the default gathering
    because a strategy node is not registered in the builder's node memo, so
    substituting a variant "by name" would silently rebuild the original.
    """
    params = ctxt.mkParams(task)
    sel = Selection.from_params(params)

    expand = getattr(ctxt, "expand", None)
    plans = [plan_need(need, sel, expand) for need in ctxt.declaredNeeds(task)]
    check_selection(sel, plans)

    # Needs this elaborator wires itself: everything dropped, plus every suite
    # rebuilt as a variant. Keyed by name because `select_needs` is invoked once
    # per `uses`-chain level and must be idempotent across those calls.
    withheld = {p.task.name for p in plans if not p.keep or p.variant is not None}

    node = ctxt.buildDefault(
        task, name,
        select_needs=lambda needs: [n for n in needs if n.name not in withheld])

    for p in plans:
        if p.keep and p.variant is not None:
            ctxt.wireNeed(node, ctxt.mkTaskNode(p.variant, name=p.task.name))

    if sel.active:
        dropped = [p.task.name for p in plans if not p.keep]
        _log.debug("test selection: tests=%s views=%s dropped=%s",
                   sel.tests, sel.views, dropped)

    return node
