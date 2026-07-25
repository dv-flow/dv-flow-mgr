#****************************************************************************
#* test_info.py
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
"""Test-inventory introspection: the elaborator behind `std.TestInfo`.

`std.TestRunner` answers "run these tests"; this answers "what tests are
there?" -- the names `--tests` and `--views` accept, without building or
running anything.

The inventory is read off ANOTHER task -- the project's test-running root --
named by the `target` parameter. That is deliberate: an info task that carried
its own copy of the runner's `needs:` would drift the moment a suite was added,
and the whole point is to report what the runner would actually run. There is
no `needs: [<other-task>.needs]` syntax in dv-flow; the equivalent is done here,
where an elaborator can resolve the target task type (`ctxt.getTask`) and read
its declared needs (`ctxt.declaredNeeds`) without building any of them.

Nothing upstream is built: the info node drops every declared need
(`select_needs -> []`), so `dfm run tests-info` compiles no images and runs no
simulations. The enumeration happens at graph-build time, in the elaborator,
and rides to the run callable as a JSON blob on the node's `inventory` param.

Classification reuses `test_select.plan_need` with an empty selection, so what
this reports and what `--tests`/`--views` select over cannot disagree.
"""

import dataclasses as dc
import json
import logging
from typing import Any, Dict, List, Optional

from .test_select import Plan, Selection, plan_need

_log = logging.getLogger("test_info")


class TargetError(Exception):
    """The task to introspect could not be resolved. Raised rather than
    reported-and-continued for the same reason `SelectionError` is: an empty
    inventory reads as "this project has no tests", which is exactly the wrong
    thing to tell someone asking what tests exist."""


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def resolve_target(ctxt, task, target : str):
    """The task type named by `target`, or None.

    A bare name (`tests`) is looked up in the info task's own package first --
    `task.name` is fully qualified (`<pkg>.tests-info`), so its prefix is the
    package to try. That is what lets a base project write `target: tests` once
    and have it bind in every leaf that uses the project.
    """
    if not target:
        return None

    candidates : List[str] = []
    if "." not in target:
        name = getattr(task, "name", "") or ""
        if "." in name:
            candidates.append("%s.%s" % (name.rsplit(".", 1)[0], target))
    candidates.append(target)

    for candidate in candidates:
        found = ctxt.getTask(candidate)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _entry(plan : Plan) -> Dict[str, Any]:
    name = getattr(plan.task, "name", "") or ""
    scope, _, short = name.rpartition(".")
    return {
        "name": name,
        # A task name IS a path (`fw-wb-dma.uvm.uvm-universal`), so the scope it
        # was declared in is data the report can group by rather than a string
        # the reader has to parse out of every row.
        "scope": scope,
        "short": short or name,
        "cases": list(plan.cases),
        "views": list(plan.views),
        "views_open": bool(plan.views_open),
    }


def build_inventory(ctxt, target_task, sel : Selection) -> Dict[str, Any]:
    """Enumerate what `target_task` offers, without building any of it."""
    expand = getattr(ctxt, "expand", None)
    plans = [plan_need(need, sel, expand)
             for need in ctxt.declaredNeeds(target_task)]

    suites = [_entry(p) for p in plans if p.is_test]
    other = [getattr(p.task, "name", "") or "" for p in plans if not p.is_test]

    cases : List[str] = []
    views : List[str] = []
    for p in plans:
        for c in p.cases:
            if c and c not in cases:
                cases.append(c)
        for v in p.views:
            if v and v not in views:
                views.append(v)

    return {
        "target": getattr(target_task, "name", "") or "",
        "test_key": sel.test_key,
        "view_axis": sel.view_axis,
        "cases": cases,
        "views": views,
        # A suite whose view axis is an unresolvable expression: its members are
        # not knowable here, and the report must say so rather than imply the
        # list is complete.
        "views_open": any(p.views_open for p in plans),
        "suites": suites,
        "other": other,
    }


# ---------------------------------------------------------------------------
# The elaborator
# ---------------------------------------------------------------------------

def TestInfo(ctxt, task, name):
    """`elaborate:` entry point for `std.TestInfo`."""
    params = ctxt.mkParams(task)
    sel = Selection(
        test_key=getattr(params, "test_key", None) or "name",
        view_axis=getattr(params, "view_axis", None) or "view")
    target = str(getattr(params, "target", "") or "")

    target_task = resolve_target(ctxt, task, target)

    if target_task is None:
        raise TargetError(
            "no task named '%s' to introspect. Set `target:` to the project's "
            "test-running root (the task that `uses: std.TestRunner`)." % target)

    inventory = build_inventory(ctxt, target_task, sel)
    _log.debug("test-info: target=%s cases=%s views=%s",
               inventory["target"], inventory["cases"], inventory["views"])

    # Build nothing upstream: an inventory must never trigger a compile.
    node = ctxt.buildDefault(task, name, select_needs=lambda needs: [])
    if getattr(node, "params", None) is not None:
        node.params.inventory = json.dumps(inventory)
    return node


# ---------------------------------------------------------------------------
# The run callable
# ---------------------------------------------------------------------------

async def TestInfoRun(runner, input):
    """Writes the inventory to `tests-info.json` in the rundir. The console
    rendering is the `summary:` hook below -- so the data is available to a
    script and the presentation to a human, from one enumeration."""
    from dv_flow.mgr import TaskDataResult
    import os

    raw = getattr(input.params, "inventory", "") or "{}"
    path = os.path.join(input.rundir, "tests-info.json")
    try:
        os.makedirs(input.rundir, exist_ok=True)
        with open(path, "w") as fp:
            fp.write(raw)
    except OSError as e:
        _log.warning("test-info: could not write %s: %s", path, e)

    return TaskDataResult()


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------
#
# A task name is a path, and the scopes it passes through are the project's own
# structure (`fw-wb-dma.uvm` holds the UVM suites). Flattening that to one
# fully-qualified name per row repeats the shared prefix on every line and
# leaves the reader to spot what is a sibling of what.

def scope_rows(suites : List[Dict[str, Any]]):
    """`suites` as `(depth, label, suite_or_None)` rows: a scope header, then
    the suites declared in it, then nested scopes.

    Declaration order is preserved -- it is the order the flow file is written
    in, which is the order the author thinks about them in. A scope with one
    child and no suites of its own is joined onto its child (`fw-wb-dma.uvm`,
    not `fw-wb-dma` > `uvm`): the intermediate node carries no information a
    reader needs, and indenting for it wastes the width the case list wants.
    """
    root : Dict[str, Any] = {"children": {}, "suites": []}

    for s in suites:
        node = root
        for part in [p for p in (s.get("scope") or "").split(".") if p]:
            node = node["children"].setdefault(
                part, {"children": {}, "suites": []})
        node["suites"].append(s)

    rows = []

    def walk(node, label, depth):
        # Collapse a chain of single-child, suite-less scopes into one label.
        while (not node["suites"] and len(node["children"]) == 1):
            part, child = next(iter(node["children"].items()))
            label = ("%s.%s" % (label, part)) if label else part
            node = child

        next_depth = depth
        if label:
            rows.append((depth, label, None))
            next_depth = depth + 1

        for s in node["suites"]:
            rows.append((next_depth, s.get("short") or s.get("name") or "", s))
        for part, child in node["children"].items():
            walk(child, part, next_depth)

    walk(root, "", 0)
    return rows


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def _fmt(values, open_ended=False) -> str:
    text = ", ".join(values) if values else "(none)"
    return (text + ", ...") if open_ended else text


def test_info_summary(ctxt):
    """`summary:` callable: render the inventory."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table

    params = getattr(getattr(ctxt, "root", None), "params", None)
    raw = getattr(params, "inventory", "") if params is not None else ""
    try:
        inv = json.loads(raw) if raw else {}
    except ValueError:
        inv = {}

    if not inv:
        return ctxt.task_summary()

    blocks = []

    header = Table.grid(padding=(0, 2))
    header.add_column(justify="left", style="bold")
    header.add_column(justify="left")
    header.add_row("cases", _fmt(inv.get("cases") or []))
    header.add_row("views", _fmt(inv.get("views") or [],
                                 inv.get("views_open", False)))
    blocks.append(header)

    suites = inv.get("suites") or []
    if suites:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_row("[dim]suite[/dim]", "[dim]views[/dim]", "[dim]cases[/dim]")
        for depth, label, suite in scope_rows(suites):
            indent = "  " * depth
            if suite is None:
                # A scope: structure, not a runnable thing -- no case columns.
                table.add_row("%s[dim]%s[/dim]" % (indent, label))
                continue
            table.add_row(
                indent + label,
                _fmt(suite.get("views") or [], suite.get("views_open", False)),
                _fmt(suite.get("cases") or []))
        blocks.append(table)

    usage = (
        "[dim]dfm run %s --tests <case>[,<case>]  --views <view>[,<view>][/dim]"
        % (inv.get("target") or "tests"))
    blocks.append(usage)

    return Panel(Group(*blocks),
                 title="Test inventory (%s)" % (inv.get("target") or "?"),
                 border_style="cyan")
