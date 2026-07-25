#****************************************************************************
#* summary_builtin.py
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
"""The `task-summary` builtin: a post-run roll-up over the completed node graph.

A near-identical view already existed as `TaskListenerProgress._final_panel()`,
but it rendered from listener-accumulated state (observation order, live rich
progress rows) and so ran *only* in the `progress` UI -- which is auto-selected
only on a TTY with logging off. Piped and CI runs, the ones that most need a
summary, got nothing.

This rebuilds the same view over `TaskNode.result`, which is populated on every
execution path including remote (`task_runner.py:670` <- `daemon_client.py:192`),
so it is backend-independent and UI-independent. The progress listener now
delegates here rather than keeping a second implementation.

Deliberately *not* disk-backed, unlike `TaskListenerReport`: `cache_hit`,
`cache_stored` and `base_hit` are runtime-only and are never written to
`exec_data.json`, so memory is the strictly better source here. Disk is the
fallback for the one case memory cannot cover -- a node whose `.result` is None.
"""

import dataclasses as dc
import os
from typing import Any, Dict, List, Optional

from .task_data import SeverityE


# Status codes, in the order they are tested. Matches the legend the progress
# listener established (E/W/C/B/U/D), with '?' for a node that never produced a
# result.
ERROR = 'E'
WARNING = 'W'
CACHE_HIT = 'C'
BASE_HIT = 'B'
UPTODATE = 'U'
DONE = 'D'
UNKNOWN = '?'

_STATUS_LABEL = {
    ERROR: 'error',
    WARNING: 'warning',
    CACHE_HIT: 'cache-hit',
    BASE_HIT: 'base-hit',
    UPTODATE: 'up-to-date',
    DONE: 'done',
    UNKNOWN: 'unknown',
}

_STATUS_STYLE = {
    ERROR: 'red',
    WARNING: 'yellow',
    CACHE_HIT: 'magenta',
    BASE_HIT: 'cyan',
    UPTODATE: 'blue',
    DONE: 'green',
    UNKNOWN: 'dim',
}

# Statuses worth showing when not verbose. A run of 200 up-to-date tasks should
# summarize as a count, not 200 rows.
_NOISY = (ERROR, WARNING, DONE, UNKNOWN)


@dc.dataclass
class TaskFacts:
    """What the summary knows about one node."""
    node : Any
    name : str
    status : str
    markers : List[Any] = dc.field(default_factory=list)
    elapsed : Optional[float] = None
    errors : int = 0
    warnings : int = 0

    @property
    def label(self) -> str:
        return _STATUS_LABEL[self.status]


def _display_name(node) -> str:
    getter = getattr(node, '_get_display_name', None)
    if getter is not None:
        try:
            return getter()
        except Exception:
            pass
    return node.name or "<anon>"


def _elapsed_s(node) -> Optional[float]:
    start = getattr(node, 'start', None)
    end = getattr(node, 'end', None)
    if start is None or end is None:
        return None
    try:
        return (end - start).total_seconds()
    except Exception:
        return None


def format_elapsed(seconds : Optional[float]) -> str:
    if seconds is None:
        return ""
    if seconds >= 1.0:
        return "%0.2fs" % seconds
    return "%0.2fms" % (seconds * 1000)


def _load_disk_result(node):
    """Fallback for a node with no in-memory result: the exec_data.json it wrote.

    This is the inverse of `TaskListenerReport`, which prefers disk. It cannot
    recover the cache/base flags (they are never persisted), so a node recovered
    this way is classified on status and markers alone.
    """
    rundir = getattr(node, 'rundir', None)
    if not rundir:
        return None
    path = rundir[0] if len(rundir) == 1 and os.path.isabs(rundir[0]) else os.path.join(*rundir)
    path = os.path.join(path, "exec_data.json")
    if not os.path.isfile(path):
        return None
    try:
        import json
        with open(path, "r") as fp:
            return json.load(fp)
    except Exception:
        return None


def _facts_for(node) -> TaskFacts:
    name = _display_name(node)
    elapsed = _elapsed_s(node)
    result = getattr(node, 'result', None)

    if result is None:
        data = _load_disk_result(node)
        if data is None:
            return TaskFacts(node=node, name=name, status=UNKNOWN, elapsed=elapsed)
        status_v = data.get('status', 0)
        markers = data.get('markers', []) or []
        errors = sum(1 for m in markers if _severity_of(m) == SeverityE.Error)
        warnings = sum(1 for m in markers if _severity_of(m) == SeverityE.Warning)
        status = ERROR if (status_v != 0 or errors) else (WARNING if warnings else DONE)
        return TaskFacts(node=node, name=name, status=status, markers=list(markers),
                         elapsed=elapsed, errors=errors, warnings=warnings)

    markers = list(result.markers or [])
    errors = sum(1 for m in markers if _severity_of(m) == SeverityE.Error)
    warnings = sum(1 for m in markers if _severity_of(m) == SeverityE.Warning)

    # Order matters and mirrors the progress listener: a failing cache hit is
    # still a failure.
    if result.status != 0 or errors > 0:
        status = ERROR
    elif warnings > 0:
        status = WARNING
    elif getattr(result, 'cache_hit', False):
        status = CACHE_HIT
    elif getattr(result, 'base_hit', False):
        status = BASE_HIT
    elif not result.changed:
        status = UPTODATE
    else:
        status = DONE

    return TaskFacts(node=node, name=name, status=status, markers=markers,
                     elapsed=elapsed, errors=errors, warnings=warnings)


def _severity_of(marker):
    sev = getattr(marker, 'severity', None)
    if sev is not None:
        return sev
    if isinstance(marker, dict):
        raw = marker.get('severity')
        for s in SeverityE:
            if raw == s or raw == str(s) or raw == getattr(s, 'value', None):
                return s
    return None


def _marker_text(marker) -> str:
    msg = getattr(marker, 'msg', None)
    if msg is None and isinstance(marker, dict):
        msg = marker.get('msg', '')
    sev = _severity_of(marker)
    prefix = {SeverityE.Error: 'E', SeverityE.Warning: 'W', SeverityE.Info: 'I'}.get(sev, ' ')
    loc = getattr(marker, 'loc', None)
    if loc is None and isinstance(marker, dict):
        loc = marker.get('loc')
    loc_s = ""
    path = getattr(loc, 'path', None) if loc is not None else None
    if path is None and isinstance(loc, dict):
        path = loc.get('path')
    if path:
        line = getattr(loc, 'line', None) if not isinstance(loc, dict) else loc.get('line')
        loc_s = " (%s%s)" % (path, ":%d" % line if line not in (None, -1) else "")
    return "%s: %s%s" % (prefix, msg or "", loc_s)


def dep_map(roots) -> Dict[Any, set]:
    """Node -> set of nodes it depends on, over the whole reachable subgraph.

    Equivalent to `TaskSetRunner.buildDepMap` but free of the runner, so the
    summary can be built from nodes alone (the progress listener has no runner
    handle at render time).
    """
    roots = roots if isinstance(roots, (list, tuple)) else [roots]
    dep_m = {}

    def visit(node):
        if node is None or node in dep_m:
            return
        needs = [n[0] for n in getattr(node, 'needs', [])]
        dep_m[node] = set(needs)
        for n in needs:
            visit(n)
        # Compound tasks own subtasks that are not reachable through `needs`.
        for sub in getattr(node, 'tasks', []) or []:
            if sub is not node:
                dep_m[node].add(sub)
                visit(sub)

    for r in roots:
        visit(r)
    return dep_m


def ordered_nodes(roots) -> List[Any]:
    """The reachable subgraph in dependency order (dependencies first).

    The progress listener used observation order, which is unavailable here.
    Topological order is the deterministic stand-in, and it also makes the same
    run render identically twice -- which `--summary-file` depends on.
    """
    from toposort import toposort

    dep_m = dep_map(roots)
    ret = []
    for group in toposort(dep_m):
        ret.extend(sorted(group, key=lambda n: _display_name(n)))
    return ret


def collect_task_facts(roots) -> List[TaskFacts]:
    return [_facts_for(n) for n in ordered_nodes(roots)]


def count_facts(facts : List[TaskFacts]) -> Dict[str, int]:
    counts = {k: 0 for k in _STATUS_LABEL}
    for f in facts:
        counts[f.status] += 1
    counts['total'] = len(facts)
    return counts


def summary_title(counts : Dict[str, int], cache_enabled : bool = False) -> str:
    """The count line. Same fields, and the same "omit if zero" rule, as the
    panel title the progress UI has always shown."""
    parts = ["Total: %d" % counts['total']]
    if counts[UPTODATE]:
        parts.append("Up-to-date: %d" % counts[UPTODATE])
    if counts[BASE_HIT]:
        parts.append("Base: %d" % counts[BASE_HIT])
    if cache_enabled:
        miss = counts[DONE] + counts[ERROR] + counts[WARNING]
        parts.append("Cache: %d hit / %d miss" % (counts[CACHE_HIT], miss))
    if counts[DONE]:
        parts.append("Done: %d" % counts[DONE])
    if counts[ERROR]:
        parts.append("Errors: %d" % counts[ERROR])
    if counts[WARNING]:
        parts.append("Warnings: %d" % counts[WARNING])
    if counts[UNKNOWN]:
        parts.append("Unknown: %d" % counts[UNKNOWN])
    return " | ".join(parts)


def _rows(facts : List[TaskFacts], verbose : bool) -> List[TaskFacts]:
    if verbose:
        return facts
    return [f for f in facts if f.status in _NOISY or f.markers]


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def build_task_summary(roots, verbose : bool = False, cache_enabled : bool = False):
    """The rich renderable. This is what `summary.task_summary()` hands to a
    custom summary so it can compose rather than reimplement."""
    from rich.panel import Panel
    from rich.table import Table

    facts = collect_task_facts(roots)
    counts = count_facts(facts)

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left")
    rows = _rows(facts, verbose)
    if not rows:
        # An all-up-to-date run has no interesting rows; an empty box reads as
        # a bug, so say so. The counts are in the title.
        table.add_row("[dim]nothing to report[/dim]")
    for f in rows:
        style = _STATUS_STYLE[f.status]
        elapsed = format_elapsed(f.elapsed)
        line = "[%s]%s[/%s] %s" % (style, f.status, style, f.name.replace("[", "\\["))
        if elapsed:
            line += " [dim]%s[/dim]" % elapsed
        table.add_row(line)
        for m in f.markers:
            table.add_row("  " + _marker_text(m).replace("[", "\\["))

    return Panel(table, title="Task Summary (%s)" % summary_title(counts, cache_enabled),
                 border_style="blue")


def render_task_summary_text(roots, verbose : bool = False,
                             cache_enabled : bool = False) -> str:
    """Plain text. No ANSI and no terminal-width dependence, so the same run
    produces the same bytes locally and in CI."""
    facts = collect_task_facts(roots)
    counts = count_facts(facts)

    lines = ["Task Summary (%s)" % summary_title(counts, cache_enabled)]
    rows = _rows(facts, verbose)
    if rows:
        width = max(len(f.name) for f in rows)
        for f in rows:
            line = "  %s %s" % (f.status, f.name.ljust(width))
            elapsed = format_elapsed(f.elapsed)
            if elapsed:
                line += "  " + elapsed
            lines.append(line.rstrip())
            for m in f.markers:
                lines.append("      " + _marker_text(m))
    return "\n".join(lines)


def render_task_summary_markdown(roots, verbose : bool = False,
                                 cache_enabled : bool = False) -> str:
    """Real markdown -- headings and a table -- rather than a fenced block of
    box-drawing characters. Mirrors `TaskListenerReport._write_markdown`, which
    is what makes it usable as a GitHub job summary."""
    facts = collect_task_facts(roots)
    counts = count_facts(facts)
    rows = _rows(facts, verbose)

    lines = ["## Task Summary", ""]
    lines.append("- **Tasks:** %d" % counts['total'])
    for code in (DONE, UPTODATE, CACHE_HIT, BASE_HIT, ERROR, WARNING, UNKNOWN):
        if counts[code]:
            lines.append("- **%s:** %d" % (_STATUS_LABEL[code].capitalize(), counts[code]))
    lines.append("")

    if rows:
        lines.append("| Status | Task | Time |")
        lines.append("|---|---|---|")
        for f in rows:
            lines.append("| %s | `%s` | %s |" % (
                f.label, f.name, format_elapsed(f.elapsed) or "-"))
        lines.append("")

    marker_rows = [f for f in facts if f.markers]
    if marker_rows:
        lines.append("### Markers")
        lines.append("")
        for f in marker_rows:
            lines.append("- `%s`" % f.name)
            for m in f.markers:
                lines.append("  - %s" % _marker_text(m))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
