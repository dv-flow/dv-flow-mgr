#****************************************************************************
#* render_text.py -- results.json as console text
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
"""The console view of a run record: a tree with a status, the name, the
headline and a few metrics per node. Passing subtrees collapse to one line;
failing nodes show their failing checks, log location and waves. Pure: it
takes a ``ResultsFile`` and returns text."""
import os
from typing import List, Optional

from .model import ResultNode, ResultsFile
from .rollup import leaf_counts
from .status import is_ok
from .summary import first_artifact, log_ref

STATUS_WORD = {"pass": "pass", "fail": "FAIL", "error": "ERROR",
               "timeout": "TIMEOUT", "skip": "skip", "notrun": "NOTRUN"}
_MAX_METRICS = 4


def fmt_value(v: float) -> str:
    if float(v).is_integer() and abs(v) < 1e15:
        return "%d" % v
    return "%.4g" % v


def fmt_metric(name, m) -> str:
    return "%s=%s%s" % (name, fmt_value(m.value), (" " + m.unit) if m.unit else "")


def fmt_check(c) -> str:
    s = "check %s: %s" % (c.name, c.status)
    if c.metric and c.op:
        v = fmt_value(c.value) if c.value is not None else "?"
        s += " (%s=%s, want %s %s)" % (c.metric, v, c.op, c.goal)
    if c.msg:
        s += " -- %s" % c.msg
    return s


def _metrics(node: ResultNode) -> str:
    """The first few metrics, those a check reads first (they explain the
    verdict), then in the order the producer gave them."""
    checked = [c.metric for c in node.checks if c.metric in node.metrics]
    names = list(dict.fromkeys(checked + list(node.metrics.keys())))[:_MAX_METRICS]
    items = [(k, node.metrics[k]) for k in names]
    return "  ".join(fmt_metric(k, m) for k, m in items)


def _stale_tag(node: ResultNode, path: Optional[str]) -> str:
    if not path:
        return ""
    for a in node.artifacts:
        for st in a.stamps:
            if st.path == path and st.state in ("stale", "missing"):
                return " [%s]" % st.state
    return ""


def _line(node: ResultNode, show_metrics=True) -> str:
    # A root raised to error by its `_tasks` shows its own status; the
    # `_tasks` subtree below it shows why the run errored.
    own = getattr(node, "own_status", None) or node.status
    parts = [node.name or "<root>", STATUS_WORD.get(own, own)]
    if node.msg:
        parts.append(node.msg)
    if node.reused:
        parts.append("[reused]")
    m = _metrics(node) if show_metrics else ""
    if m:
        parts.append("(" + m + ")")
    return "  ".join(parts)


def _details(node: ResultNode) -> List[str]:
    ret = []
    for c in node.checks:
        if c.status in ("fail", "error"):
            ret.append(fmt_check(c))
    shown = 0
    for d in node.diagnostics:
        if d.severity not in ("error", "fatal") or shown >= 3 or d.msg == node.msg:
            continue
        loc = ""
        if d.loc is not None and d.loc.line is not None:
            loc = " (line %d)" % d.loc.line
        ret.append("%s: %s%s" % (d.severity, d.msg, loc))
        shown += 1
    lr = log_ref(node)
    if lr is not None:
        ret.append("log: %s%s%s" % (lr["path"], (":%d" % lr["line"]) if lr.get("line") else "",
                                    _stale_tag(node, lr["path"])))
    w = first_artifact(node, "waves")
    if w:
        ret.append("waves: %s%s" % (w, _stale_tag(node, w)))
    return ret


def render_tree(rf: ResultsFile, depth: Optional[int] = None, expand: bool = False) -> str:
    """The tree. ``depth`` limits how deep to descend (the root is depth 0);
    ``expand`` shows passing subtrees in full."""
    lines = []
    run = rf.run
    root_name = run.root if isinstance(run.root, str) else ", ".join(run.root)
    lines.append("Run %s  %s  (exit %d)" % (run.id, root_name, run.exit_status))
    lines.append("")

    def visit(node: ResultNode, prefix: str, last: bool, level: int, top: bool):
        if top:
            head, cont = "", ""
        else:
            head = prefix + ("└─ " if last else "├─ ")
            cont = prefix + ("   " if last else "│  ")
        kids = node.children
        collapsed = False
        text = _line(node)
        if kids and is_ok(node.status) and not expand:
            c = leaf_counts(kids)
            text += "  [%d passed]" % c.get("pass", 0) if c.get("total") == c.get("pass") \
                else "  [%d results]" % c.get("total", 0)
            collapsed = True
        lines.append(head + text)
        if not is_ok(getattr(node, "own_status", None) or node.status):
            bar = "│  " if kids and not collapsed and (depth is None or level < depth) else "   "
            for d in _details(node):
                lines.append(cont + bar + d)
        if collapsed or (depth is not None and level >= depth):
            if kids and not collapsed:
                lines.append(cont + "└─ ... %d more" % len(kids))
            return
        for i, k in enumerate(kids):
            visit(k, cont, i == len(kids) - 1, level + 1, False)

    visit(rf.result, "", True, 0, True)
    lines.append("")
    lines.append(render_counts(rf))
    return "\n".join(lines) + "\n"


def render_counts(rf: ResultsFile) -> str:
    s = rf.summary
    c = s.counts
    parts = ["%s: %s" % (STATUS_WORD.get(s.status, s.status), s.msg)] if s.msg else \
        [STATUS_WORD.get(s.status, s.status)]
    cs = ", ".join("%s %d" % (k, c[k]) for k in ("pass", "fail", "error", "timeout", "notrun", "skip")
                   if c.get(k))
    parts.append("total %d%s" % (c.get("total", 0), (": " + cs) if cs else ""))
    wt = s.metrics.get("walltime_s")
    if wt is not None:
        parts.append("%.1fs" % wt.value)
    return "  |  ".join(parts)


def render_failures(rf: ResultsFile) -> str:
    """Just the summary's failure list."""
    s = rf.summary
    lines = [render_counts(rf)]
    for f in s.failures:
        lines.append("")
        lines.append("%s  %s%s" % (STATUS_WORD.get(f.status, f.status), f.path,
                                   ("  " + f.msg) if f.msg else ""))
        for c in f.checks:
            lines.append("    " + fmt_check(c))
        if f.log is not None:
            lines.append("    log: %s%s" % (f.log.path, (":%d" % f.log.line) if f.log.line else ""))
        if f.waves:
            lines.append("    waves: %s" % f.waves)
    return "\n".join(lines) + "\n"


def render_list(records) -> str:
    """``records``: ``[(run_id, ResultsFile | None)]``, newest first."""
    lines = []
    for rid, rf in records:
        if rf is None:
            lines.append("%-20s  (unreadable)" % rid)
            continue
        root = rf.run.root if isinstance(rf.run.root, str) else ",".join(rf.run.root)
        c = rf.summary.counts
        lines.append("%-20s  %-7s  %-32s  %d/%d passed" % (
            rid, STATUS_WORD.get(rf.summary.status, rf.summary.status), root,
            c.get("pass", 0), c.get("total", 0)))
    return "\n".join(lines) + ("\n" if lines else "")
