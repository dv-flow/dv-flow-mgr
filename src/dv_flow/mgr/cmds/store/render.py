"""Rich rendering for `dfm store` reports: tables, inline bar charts,
colour-coded status. Agents should use --json instead (see json_doc)."""
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...rundir_store_ops import age_secs, fmt_age, fmt_size

JSON_SCHEMA = 1

STATUS_STYLE = {
    "ok": "green",
    "orphan": "red",
    "retargeted": "red",
    "unknown": "yellow",
    "stale": "yellow",
    "busy": "cyan",
    "unmanaged": "dim",
    "safe": "red",
    "review": "yellow",
}

BAR_BLOCKS = " ▏▎▍▌▋▊▉█"


def console() -> Console:
    # Wide enough for paths when piped into a log; Rich drops colour itself
    # when stdout is not a terminal.
    if sys.stdout.isatty():
        return Console(highlight=False)
    return Console(highlight=False, width=max(120, int(os.environ.get("COLUMNS", 0) or 0)))


def json_doc(kind: str, **data) -> str:
    doc = {"schema": JSON_SCHEMA, "kind": kind,
           "generated": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y-%m-%dT%H:%M:%SZ")}
    doc.update(data)
    return json.dumps(doc, indent=2)


def bar(frac: float, width: int = 20, style: str = "blue") -> Text:
    """A horizontal bar of ``width`` cells filled to ``frac`` (0..1), with
    eighth-cell resolution."""
    frac = max(0.0, min(1.0, frac or 0.0))
    eighths = int(round(frac * width * 8))
    full, part = divmod(eighths, 8)
    s = "█" * full + (BAR_BLOCKS[part] if part else "")
    t = Text(s, style=style)
    t.append("·" * (width - len(s)), style="dim")
    return t


def stacked_bar(parts: List[tuple], total: int, width: int = 40,
                min_cells: bool = False) -> Text:
    """parts: [(value, style), ...] drawn left to right as a share of total.
    With ``min_cells``, any non-zero part gets at least one cell."""
    t = Text()
    used = 0
    for i, (v, style) in enumerate(parts):
        n = int(round(width * v / total)) if total else 0
        if min_cells and v > 0 and n == 0:
            n = 1
        if i == len(parts) - 1:
            n = width - used
        n = max(0, min(n, width - used))
        t.append("█" * n, style=style)
        used += n
    return t


def status_text(s: str) -> Text:
    return Text(s, style=STATUS_STYLE.get(s, ""))


def size_text(rec) -> Text:
    if rec.size is None:
        return Text("-", style="dim")
    t = Text(fmt_size(rec.size))
    if rec.stats_stale:
        t.append("~", style="dim")
    return t


def ago(ts_age: Optional[float]) -> str:
    return "-" if ts_age is None else "%s ago" % fmt_age(ts_age)


def created_age(meta, now) -> Optional[float]:
    from ...rundir_store_entry import parse_iso
    t = parse_iso(meta.created) if meta else None
    return None if t is None else (now - t).total_seconds()


def short_path(p: Optional[str], maxlen: Optional[int] = None) -> str:
    """``~``-relative path, middle-elided to ``maxlen`` characters (keeping
    the start and the informative tail)."""
    if not p:
        return "-"
    home = os.path.expanduser("~")
    if p.startswith(home + os.sep):
        p = "~" + p[len(home):]
    if maxlen and len(p) > maxlen:
        head = max(maxlen // 3, 4)
        tail = maxlen - head - 1
        p = p[:head] + "…" + p[-tail:]
    return p


def project_of(meta) -> Optional[str]:
    """The project directory (the link's parent), for display."""
    if meta is None or not meta.link:
        return None
    return os.path.dirname(meta.link)


def entries_table(recs, now, long: bool = False, title: Optional[str] = None,
                  extra_cols: Optional[Dict[str, Any]] = None,
                  tail_cols: Optional[Dict[str, Any]] = None) -> Table:
    total = sum(r.size or 0 for r in recs)
    show_size = any(r.size is not None for r in recs)
    t = Table(box=box.SIMPLE_HEAD, title=title, title_justify="left",
              pad_edge=False, expand=False)
    t.add_column("STATUS", no_wrap=True)
    if extra_cols:
        for name in extra_cols:
            t.add_column(name)
    if show_size:
        t.add_column("SIZE", justify="right", no_wrap=True)
        t.add_column("SHARE", no_wrap=True)
    t.add_column("LAST USED", justify="right", no_wrap=True)
    t.add_column("CREATED", justify="right", no_wrap=True)
    t.add_column("RUNS", justify="right")
    users = {r.meta.user for r in recs if r.meta is not None}
    show_user = len(users) > 1
    if show_user:
        t.add_column("USER")
    t.add_column("HOST")
    t.add_column("PACKAGE")
    if long:
        t.add_column("GIT")
        t.add_column("MODIFIED", justify="right")
        t.add_column("FILES", justify="right")
    t.add_column("PROJECT", overflow="fold", no_wrap=not long)
    for name in (tail_cols or {}):
        t.add_column(name, overflow="fold", style="dim")
    for r in recs:
        m = r.meta
        row = [status_text(r.status.value)]
        if extra_cols:
            for f in extra_cols.values():
                row.append(f(r))
        if show_size:
            row.append(size_text(r))
            row.append(bar((r.size or 0) / total if total else 0, 12))
        row += [ago(age_secs(m, now)), ago(created_age(m, now)),
                str(m.sessions) if m else "-"]
        if show_user:
            row.append((m.user or "-") if m else "-")
        row += [(m.host or "-") if m else "-", (m.package or "-") if m else "-"]
        if long:
            g = (m.git or {}) if m else {}
            row.append("%s%s" % (g.get("remote") or "-",
                                 (" @" + g["branch"]) if g.get("branch") else ""))
            lm = None
            if r.stats is not None and r.stats.last_modified:
                from ...rundir_store_entry import parse_iso
                lm = (now - parse_iso(r.stats.last_modified)).total_seconds()
            row.append(ago(lm))
            row.append(str(r.stats.files) if r.stats else "-")
        row.append(short_path(project_of(m), None if long else 48)
                   if m else "(%s)" % r.name)
        for f in (tail_cols or {}).values():
            row.append(f(r))
        t.add_row(*row)
    return t


def grouped_table(title: str, rows: List[Dict[str, Any]], total: int,
                  key_label: str, style_by_key: bool = False,
                  limit: Optional[int] = None, width: int = 24) -> Table:
    t = Table(box=box.SIMPLE_HEAD, title=title, title_justify="left",
              title_style="bold", pad_edge=False)
    t.add_column(key_label)
    t.add_column("ENTRIES", justify="right")
    t.add_column("SIZE", justify="right")
    t.add_column("", no_wrap=True)
    t.add_column("%", justify="right")
    shown = rows if limit is None else rows[:limit]
    for e in shown:
        style = STATUS_STYLE.get(e["key"], "blue") if style_by_key else "blue"
        frac = e["size"] / total if total else 0
        t.add_row(Text(str(e["key"]), style=style if style_by_key else ""),
                  str(e["count"]), fmt_size(e["size"]),
                  bar(frac, width, style), "%.0f%%" % (100 * frac))
    if limit is not None and len(rows) > limit:
        rest = rows[limit:]
        t.add_row(Text("(%d more)" % len(rest), style="dim"),
                  str(sum(e["count"] for e in rest)),
                  fmt_size(sum(e["size"] for e in rest)), "", "")
    return t


def fs_panel(store: str, fs: Optional[Dict[str, int]], store_size: int) -> Panel:
    if not fs or not fs.get("total"):
        return Panel(Text("filesystem usage unavailable", style="dim"),
                     title="Filesystem", title_align="left")
    total, free, used = fs["total"], fs["free"], fs["used"]
    other = max(used - store_size, 0)
    b = stacked_bar([(store_size, "magenta"), (other, "grey50"), (free, "green")],
                    total, 50, min_cells=True)
    leg = Text()
    leg.append("█ ", style="magenta")
    leg.append("store %s (%.0f%%)   " % (fmt_size(store_size), 100.0 * store_size / total))
    leg.append("█ ", style="grey50")
    leg.append("other %s   " % fmt_size(other))
    leg.append("█ ", style="green")
    leg.append("free %s of %s" % (fmt_size(free), fmt_size(total)))
    warn = None
    if free / total < 0.10:
        warn = Text("Filesystem is %.0f%% full" % (100.0 * used / total), style="bold red")
    body = [Text(store, style="bold"), b, leg]
    if warn is not None:
        body.append(warn)
    return Panel(Group(*body), title="Filesystem", title_align="left")


def actions_panel(lines: List[tuple]) -> Optional[Panel]:
    """lines: [(comment, command), ...]"""
    if not lines:
        return None
    t = Text()
    for i, (c, cmd) in enumerate(lines):
        if i:
            t.append("\n")
        t.append("# %s\n" % c, style="dim")
        t.append(cmd, style="bold cyan")
    return Panel(t, title="Suggested actions", title_align="left",
                 border_style="cyan")


def compact_table(rows, now, title: Optional[str] = None,
                  label: str = "TIER") -> Table:
    """Compact what/how-big/why table. rows: [(rec, tag, reason), ...];
    ``tag`` (a tier or status) is colour-coded."""
    total = sum(r.size or 0 for r, _, _ in rows)
    t = Table(box=box.SIMPLE_HEAD, title=title, title_justify="left",
              pad_edge=False)
    t.add_column(label, no_wrap=True)
    t.add_column("SIZE", justify="right", no_wrap=True)
    t.add_column("SHARE", no_wrap=True)
    t.add_column("LAST USED", justify="right", no_wrap=True)
    t.add_column("PACKAGE", no_wrap=True)
    t.add_column("WHY", style="dim", overflow="fold", min_width=24)
    t.add_column("PROJECT", no_wrap=True)
    for r, tag, reason in rows:
        m = r.meta
        style = STATUS_STYLE.get(tag, "")
        t.add_row(Text(tag, style=style), size_text(r),
                  bar((r.size or 0) / total if total else 0, 12, style or "blue"),
                  ago(age_secs(m, now)), (m.package or "-") if m else "-",
                  reason, short_path(project_of(m), 40) if m else "(%s)" % r.name)
    return t


def candidates_table(cands, now, title: Optional[str] = None) -> Table:
    return compact_table([(c.rec, c.tier, c.reason) for c in cands], now, title)


def entry_cards(recs, now) -> Group:
    """One detail block per entry (``list --long``): every fact, full paths."""
    from ...rundir_store_entry import parse_iso
    total = sum(r.size or 0 for r in recs)
    out = []
    for r in recs:
        m = r.meta
        g = Table.grid(padding=(0, 2))
        g.add_column(style="dim", no_wrap=True)
        g.add_column(overflow="fold")
        head = Text()
        head.append(r.status.value, style=STATUS_STYLE.get(r.status.value, ""))
        head.append("  ")
        head.append(short_path(project_of(m)) if m else "(%s)" % r.name, style="bold")
        if r.size is not None:
            sz = size_text(r)
            sz.append("  ")
            sz.append_text(bar(r.size / total if total else 0, 20))
            sz.append("  %.0f%% of listed" % (100.0 * r.size / total if total else 0),
                      style="dim")
            g.add_row("size", sz)
            g.add_row("contents", "%d files, %d dirs, %s apparent" % (
                r.stats.files, r.stats.dirs, fmt_size(r.stats.apparent)))
            if r.stats.top:
                g.add_row("largest", ", ".join("%s %s" % (n, fmt_size(v))
                                               for n, v in r.stats.top[:5]))
            if r.stats.last_modified:
                lm = (now - parse_iso(r.stats.last_modified)).total_seconds()
                g.add_row("modified", "%s (%s)" % (ago(lm), r.stats.last_modified))
        if m is not None:
            g.add_row("last used", "%s (%s), %d session%s" % (
                ago(age_secs(m, now)), m.last_used, m.sessions or 0,
                "" if m.sessions == 1 else "s"))
            g.add_row("created", "%s (%s)" % (ago(created_age(m, now)), m.created))
            g.add_row("owner", "%s on %s" % (m.user or "?", m.host or "?"))
            g.add_row("package", m.package or "-")
            gi = m.git or {}
            if gi.get("remote"):
                g.add_row("git", "%s @ %s" % (gi["remote"], gi.get("branch") or "?"))
            g.add_row("link", m.link)
            g.add_row("source", m.store_source or "-")
        g.add_row("entry", r.path)
        out.append(head)
        out.append(g)
        out.append(Text(""))
    return Group(*out)
