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
`--requires` elaborates the target's graph to find each run's producers, but
wires none of it to this node, so it still executes nothing.

Classification and selection are `test_select.build_tree` + `resolve` -- the
same calls the runner makes -- so `tests-info --tests sanity.` reports exactly
what `tests --tests sanity.` would run, and rejects exactly what it would
reject.

Output is chosen by `format` (or the `json` shorthand). In a machine format the
summary hook returns the payload as a plain string and the elaborator marks the
node `machine_output`, which tells `dfm run` to keep its own progress output off
stdout -- so `dfm run tests-info --json | jq` works.
"""

import dataclasses as dc
import json
import logging
from typing import Any, Dict, List, Optional

from .test_select import (Selection, SelectionError, Tree, Resolution,
                          Pattern, build_tree, resolve, format_path,
                          parse_requires, run_requires, warn_unproduced)

# Version of the machine-readable inventory. Bump on an incompatible change, so
# a script consuming `--json` can refuse a shape it does not understand.
SCHEMA_VERSION = 1

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

def build_inventory(tree : Tree, res : Resolution,
                    target : str = "",
                    instances : bool = False) -> Dict[str, Any]:
    """The inventory of what `tree` offers, narrowed to the selection in `res`.

    `suites` holds one row per *test container* -- a matrix suite or a single
    test -- grouped by the suite path it sits under, which is what the console
    report renders. `tests` is the flat list of selected tests by path: what
    `--tests` accepts, and what `--format list` prints.
    """
    sel = res.selection
    kept = res.kept_tests(tree)

    tests = []
    cases : List[str] = []
    views : List[str] = []
    for t in kept:
        tviews = _test_views(tree, res, t)
        tests.append({
            "path": format_path(t.path),
            "name": t.name,
            "task": getattr(t.task, "name", "") or "",
            "views": tviews,
            "views_open": bool(t.views_open and tviews == []),
            # The other paths the same test is reachable by, through a suite
            # shared by two parents.
            "aliases": [format_path(p) for p in t.paths[1:]],
        })
        if t.name not in cases:
            cases.append(t.name)
        for v in tviews:
            if v not in views:
                views.append(v)

    rows = []
    seen = set()
    for t in kept:
        task_name = getattr(t.task, "name", "") or ""
        if t.key[1] is not None:
            # A matrix cell: one row for the whole suite.
            if task_name in seen:
                continue
            seen.add(task_name)
            suite = tree.suites[task_name]
            suite_cases = [k[1] for k in suite.tests if res.kept.get(k)]
            row_path = suite.path
        else:
            suite_cases = [t.name]
            row_path = t.path
        tviews = _test_views(tree, res, t)
        rows.append({
            "name": task_name,
            "path": format_path(row_path),
            # Grouping key for the report: the suite the row sits under.
            "scope": format_path(row_path[:-1]),
            "short": row_path[-1],
            "cases": suite_cases,
            "views": tviews,
            "views_open": bool(t.views_open and tviews == []),
        })

    suites = []
    for name, s in tree.suites.items():
        if name in res.dropped:
            continue
        suites.append({
            "path": format_path(s.path),
            "task": name,
            "kind": s.kind,
            "aliases": [format_path(p) for p in s.paths[1:]],
        })

    for entry in tests:
        entry["selector"] = selector_for(tree, entry["path"])

    ret = {
        "schema": SCHEMA_VERSION,
        "target": target,
        "test_key": sel.test_key,
        "view_axis": sel.view_axis,
        "selection": {
            "tests": list(sel.tests),
            "views": list(sel.views),
            "exclude": list(sel.exclude),
        },
        "cases": cases,
        "views": views,
        # A suite whose view axis is an unresolvable expression: its members are
        # not knowable here, and the report must say so rather than imply the
        # list is complete.
        "views_open": any(r["views_open"] for r in rows),
        "tests": tests,
        "suites": rows,
        "suite_tree": suites,
        "other": list(tree.other),
    }
    if instances:
        ret["instances"] = build_instances(tree, res, target, tests)
    return ret


def selector_for(tree : Tree, path : str) -> str:
    """The `--tests` value that selects the test at `path` and nothing else.

    Anchored with a leading `.`: patterns match from the right, so a bare
    `x.reset` would also select `y.x.reset`. Checked rather than assumed --
    a suite and a test can share a path, and then no pattern selects just the
    one.
    """
    selector = "." + path
    pat = Pattern.parse(selector)
    hits = {k for k, t in tree.tests.items()
            if any(pat.selects(p) for p in t.paths)}
    if len(hits) != 1:
        raise SelectionError(
            "test path '%s' is not unique: '%s' selects %d tests. Rename the "
            "suite or test that shares the path." % (path, selector, len(hits)))
    return selector


def build_instances(tree : Tree, res : Resolution, target : str,
                    tests : List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per RUN -- a test on one view -- with the exact `dfm`
    arguments that run it alone.

    The unit a per-test runner schedules. `argv` is complete for the
    selection, so the caller never assembles selection syntax itself; it does
    NOT carry global options (`-c`, `-D`, project flags), which the caller
    passes the same way it passed them to `tests-info`.
    """
    out = []
    by_path = {format_path(t.path): t for t in res.kept_tests(tree)}
    for entry in tests:
        t = by_path[entry["path"]]
        views = entry["views"]
        if not views and t.views_open:
            # The view axis is an expression that could not be resolved, so the
            # runs cannot be enumerated. Listing one run that silently covers
            # every view would defeat the point of per-run entries.
            raise SelectionError(
                "cannot list runs of '%s': its views are an expression that "
                "could not be resolved here. Name them with --views."
                % entry["path"])
        for view in (views or [None]):
            argv = ["run", target, "--tests", entry["selector"]]
            if view is not None:
                argv += ["--views", view]
            out.append({
                "id": entry["path"] + ("[view=%s]" % view if view else ""),
                "test": entry["path"],
                "view": view,
                "argv": argv,
            })
    return out


def add_requires(ctxt, inv : Dict[str, Any], tree : Tree, res : Resolution,
                 sel : Selection, target : str, text : str) -> None:
    """`--requires <pattern>`: add each run's producers of `pattern`, the
    producers themselves, and the command that builds them.

    Builds the target's graph under the same selection -- elaboration only,
    nothing is wired to this node, so nothing executes. The graph is needed
    because which producer a run uses is often decided while it is built
    (`needs: [img-${{ this.view }}]`).
    """
    from .checks import _type_resolver
    want = parse_requires(text)
    root = ctxt.mkTaskNode(target, tests=list(sel.tests),
                           views=list(sel.views), exclude=list(sel.exclude))
    required = run_requires(tree, res, root, want, sel.test_key,
                            _type_resolver(ctxt))
    session_root = getattr(getattr(ctxt, "builder", None), "rundir", None)

    by_path = {format_path(t.path): t for t in res.kept_tests(tree)}
    producers : Dict[str, Dict[str, Any]] = {}
    for inst in inv["instances"]:
        nodes = required.get((by_path[inst["test"]].key, inst["view"]))
        if nodes is None:
            raise SelectionError(
                "run '%s' was not found in the built graph of '%s'"
                % (inst["id"], target))
        inst["requires"] = [n.name for n in nodes]
        for n in nodes:
            entry = producers.get(n.name)
            if entry is None:
                entry = producers[n.name] = {
                    "node": n.name,
                    "rundir": relative_rundir(n, session_root),
                    "needed_by": [],
                }
            entry["needed_by"].append(inst["id"])

    warn_unproduced([i["id"] for i in inv["instances"] if not i["requires"]],
                    len(inv["instances"]), text)

    argv = ["run", target]
    for flag, values in (("--tests", sel.tests), ("--views", sel.views),
                         ("--exclude", sel.exclude)):
        if values:
            argv += [flag, ",".join(values)]
    inv["requires"] = {"pattern": text, "produces": want}
    inv["producers"] = list(producers.values())
    inv["build"] = {"argv": argv + ["--build-only", text]}


def relative_rundir(node, session_root) -> Optional[str]:
    """Where `node` runs, relative to the session's rundir -- the path a
    `--base-rundir` lookup resolves -- or None when it cannot be told."""
    import re
    from ..task_runner import TaskSetRunner
    segs = getattr(node, "rundir", None)
    if not isinstance(segs, list) or len(segs) < 2 or session_root is None \
            or str(segs[0]) != str(session_root):
        return None
    return "/".join(re.sub(TaskSetRunner._INVALID_RUNDIR_CHARS, "_", str(s))
                    for s in segs[1:])


def _test_views(tree : Tree, res : Resolution, t) -> List[str]:
    """The views `t` will run on under the selection."""
    task_name = getattr(t.task, "name", "") or ""
    if t.view is not None:
        return [t.view] if t.view else []
    if task_name in res.run_views:
        return list(res.run_views[task_name] or [])
    return list(t.views)


# ---------------------------------------------------------------------------
# The elaborator
# ---------------------------------------------------------------------------

def TestInfo(ctxt, task, name):
    """`elaborate:` entry point for `std.TestInfo`."""
    params = ctxt.mkParams(task)
    sel = Selection.from_params(params)
    target = str(getattr(params, "target", "") or "")

    target_task = resolve_target(ctxt, task, target)

    if target_task is None:
        raise TargetError(
            "no task named '%s' to introspect. Set `target:` to the project's "
            "test-running root (the task that `uses: std.TestRunner`)." % target)

    tree = build_tree(
        target_task, ctxt.declaredNeeds,
        test_key=sel.test_key, view_axis=sel.view_axis,
        expand=getattr(ctxt, "expand", None))
    res = resolve(tree, sel)
    for w in res.warnings:
        _log.warning(w)
    requires = str(getattr(params, "requires", "") or "").strip()
    target_name = getattr(target_task, "name", "") or ""
    inventory = build_inventory(
        tree, res, target=target_name,
        instances=bool(getattr(params, "instances", False)) or bool(requires))
    if requires:
        add_requires(ctxt, inventory, tree, res, sel, target_name, requires)
    _log.debug("test-info: target=%s cases=%s views=%s",
               inventory["target"], inventory["cases"], inventory["views"])

    # Build nothing upstream: an inventory must never trigger a compile.
    node = ctxt.buildDefault(task, name, select_needs=lambda needs: [])
    if output_format(params) != "text":
        # Read by `dfm run`: the summary is the payload, so nothing else may
        # be written to stdout.
        node.machine_output = True
    if getattr(node, "params", None) is not None:
        node.params.inventory = json.dumps(inventory)
    return node


def output_format(params) -> str:
    if getattr(params, "as_json", False):
        return "json"
    return str(getattr(params, "format", "") or "text")


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
# A test path is a path, and the suites it passes through are the project's own
# structure (`regress.uart` holds the UART suites). Flattening that to one
# full path per row repeats the shared prefix on every line and leaves the
# reader to spot what is a sibling of what.

def scope_rows(suites : List[Dict[str, Any]]):
    """`suites` as `(depth, label, suite_or_None)` rows: a scope header, then
    the suites declared in it, then nested scopes.

    Declaration order is preserved -- it is the order the flow file is written
    in, which is the order the author thinks about them in. A scope with one
    child and no suites of its own is joined onto its child (`regress.uart`,
    not `regress` > `uart`): the intermediate node carries no information a
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
    from ..tui_theme import S_SECONDARY
    if not values:
        # "(none)" is the ANSWER to "what views does this suite offer?" -- an
        # empty cell would read as a rendering bug -- so it is read, and gets
        # the default foreground rather than `dim`. See tui_theme.
        return "[%s](none)[/%s]" % (S_SECONDARY, S_SECONDARY)
    text = ", ".join(values)
    return (text + ", ...") if open_ended else text


def test_info_summary(ctxt):
    """`summary:` callable: render the inventory."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table

    from ..tui_theme import S_BORDER, S_LABEL

    params = getattr(getattr(ctxt, "root", None), "params", None)
    raw = getattr(params, "inventory", "") if params is not None else ""
    try:
        inv = json.loads(raw) if raw else {}
    except ValueError:
        inv = {}

    if not inv:
        return ctxt.task_summary()

    # Machine formats: a plain string, printed verbatim.
    fmt = output_format(params)
    if fmt == "json":
        return json.dumps(inv, indent=2)
    if fmt == "yaml":
        import yaml
        return yaml.safe_dump(inv, sort_keys=False).rstrip("\n")
    if fmt == "list":
        # Each line is accepted back by `dfm run <target>`: an anchored
        # selector per test, or the full selection arguments per run.
        if "instances" in inv:
            return "\n".join(" ".join(i["argv"][2:]) for i in inv["instances"])
        return "\n".join(t["selector"] for t in inv.get("tests") or [])

    blocks = []

    header = Table.grid(padding=(0, 2))
    header.add_column(justify="left", style="bold")
    header.add_column(justify="left")
    selection = inv.get("selection") or {}
    sel_text = "  ".join(
        "--%s %s" % (k, ",".join(v)) for k, v in selection.items() if v)
    if sel_text:
        header.add_row("selection", sel_text)
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
        # The column key, and below it the scope labels: both are read, so
        # neither may be `dim`. See tui_theme.
        table.add_row(*["[bold]%s[/bold]" % c
                        for c in ("suite", "views", "cases")])
        for depth, label, suite in scope_rows(suites):
            indent = "  " * depth
            if suite is None:
                # A scope: structure, not a runnable thing -- no case columns.
                table.add_row("%s[%s]%s[/%s]" % (indent, S_LABEL, label, S_LABEL))
                continue
            table.add_row(
                indent + label,
                _fmt(suite.get("views") or [], suite.get("views_open", False)),
                _fmt(suite.get("cases") or []))
        blocks.append(table)

    producers = inv.get("producers")
    if producers is not None:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_row("[bold]producer[/bold]", "[bold]needed by[/bold]")
        for p in producers:
            n = len(p["needed_by"])
            table.add_row(p["node"], "%d run%s" % (n, "" if n == 1 else "s"))
        if not producers:
            table.add_row(_fmt([]), "")
        blocks.append(table)
        blocks.append("[%s]dfm %s[/%s]" % (
            S_LABEL, " ".join(inv["build"]["argv"]), S_LABEL))

    # The copy-paste line -- the point of running this command at all.
    usage = (
        "[%s]dfm run %s --tests <pattern>[,<pattern>]  --views <view>[,<view>][/%s]"
        % (S_LABEL, inv.get("target") or "tests", S_LABEL))
    blocks.append(usage)

    return Panel(Group(*blocks),
                 title="Test inventory (%s)" % (inv.get("target") or "?"),
                 border_style=S_BORDER)
