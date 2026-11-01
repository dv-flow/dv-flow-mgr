#****************************************************************************
#* test_summary.py
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
"""The end-of-run test report: `summary:` for `std.TestRunner`.

Reads the per-case verdicts that reached the root through ordinary dataflow and
renders "N/M passed" with per-case detail. It is deliberately *structural*
rather than typed: any item exposing `passed`/`status` is treated as a case
verdict, and any item exposing `total`/`passed` counts is treated as a roll-up.
That keeps the built-in report free of any dependency on a particular producer
-- a simulator, a formal engine, and a lint task can all feed it.

Verbosity comes from the invoked root's own `detail` parameter, so it is a
command-line argument like any other (`--detail full`). The summary receives the
root node, whose params are settled by the time it runs, so this needs no extra
plumbing.
"""

import logging

_log = logging.getLogger("test_summary")

QUIET = "quiet"
NORMAL = "normal"
FULL = "full"
_LEVELS = (QUIET, NORMAL, FULL)


def _is_case(item) -> bool:
    """A per-case verdict: something that says whether it passed."""
    return hasattr(item, "passed") and not hasattr(item, "total")


def _is_rollup(item) -> bool:
    """A suite roll-up: counts plus, usually, the member verdicts."""
    return hasattr(item, "total") and hasattr(item, "passed")


def collect_cases(output):
    """Per-case verdicts, preferring a roll-up's members over loose items.

    A roll-up carries its members by value, so taking both would count every
    case twice.
    """
    rollups = [it for it in output if _is_rollup(it)]
    if rollups:
        cases = []
        for r in rollups:
            cases.extend(getattr(r, "results", None) or getattr(r, "children", None) or [])
        if cases:
            return cases, rollups
        return [], rollups
    return [it for it in output if _is_case(it)], []


def _rollup_passed(r) -> int:
    """A roll-up's pass count. On a `std.SuiteResult` `passed` is the suite's
    own bool verdict and the count is `counts.pass` (hdlsim also keeps an
    `npassed` alias); an older roll-up carries the count in `passed`."""
    counts = getattr(r, "counts", None)
    if isinstance(counts, dict) and "pass" in counts:
        return int(counts["pass"] or 0)
    np = getattr(r, "npassed", None)
    if isinstance(np, int) and not isinstance(np, bool):
        return np
    p = getattr(r, "passed", 0)
    if isinstance(p, bool):
        return 0
    return int(p or 0)


def tally(cases, rollups):
    """(total, passed, failed, errored). Prefers the roll-up's own counts --
    the producer knows better than a structural guess what 'errored' means."""
    if rollups:
        total = sum(int(getattr(r, "total", 0) or 0) for r in rollups)
        passed = sum(_rollup_passed(r) for r in rollups)
        failed = sum(int(getattr(r, "failed", 0) or 0) for r in rollups)
        errored = sum(int(getattr(r, "errored", 0) or 0) for r in rollups)
        return total, passed, failed, errored

    total = len(cases)
    passed = sum(1 for c in cases if getattr(c, "passed", False))
    errored = sum(1 for c in cases
                  if not getattr(c, "passed", False)
                  and str(getattr(c, "status", "")) in ("error", "timeout"))
    return total, passed, total - passed - errored, errored


def _detail_level(ctxt) -> str:
    """The root's `detail` param.

    `detail` declares its value set in `flow.yaml`, so an invalid value is
    rejected before the graph runs, wherever it was set -- there is nothing left
    for this to diagnose. The fallback is only for a root that reaches the
    summary without the parameter at all.
    """
    params = getattr(getattr(ctxt, "root", None), "params", None)
    level = str(getattr(params, "detail", NORMAL) or NORMAL).lower()
    return level if level in _LEVELS else NORMAL


def _fmt_secs(v) -> str:
    """Duration -> a compact engineering string ('9.9ms', '1.2s', '3m04s').

    Fixed '%.1fs' formatting renders every sub-100ms case as '0.0s', which is
    exactly the range short unit tests live in.
    """
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        return ""
    if v >= 60:
        return "%dm%02ds" % (int(v) // 60, int(v) % 60)
    if v >= 1:
        return "%.1fs" % v
    if v >= 1e-3:
        return "%.3gms" % (v * 1e3)
    return "%.3gus" % (v * 1e6)


def _stats(case):
    """A case's `stats` map, or {}. Read structurally: any producer that
    publishes a mapping of measurements gets these columns for free."""
    s = getattr(case, "stats", None)
    return s if isinstance(s, dict) else {}


def _fmt_mem(stats) -> str:
    """Peak memory: the host process's RSS, falling back to whatever the tool
    reported about itself."""
    for key in ("maxrss_mb", "sim_mem_mb"):
        v = stats.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return "%.0fMB" % v if v >= 10 else "%.1fMB" % v
    return ""


def _fmt_simtime(stats) -> str:
    """Simulated time: the value as the tool printed it (already unit-bearing),
    else a derived seconds figure rendered with units."""
    v = stats.get("simtime")
    if isinstance(v, str) and v:
        return v
    v = stats.get("simtime_s")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return _fmt_secs(v)
    return ""


def _eng_secs(v) -> str:
    """Seconds -> engineering units with no minute form ('87us', '1.5ms', '3s').

    Separate from `_fmt_secs` because this renders the *numerator of a rate*,
    where '2m05s' would be nonsense.
    """
    for unit, mult in (("s", 1.0), ("ms", 1e-3), ("us", 1e-6),
                       ("ns", 1e-9), ("ps", 1e-12)):
        if v >= mult:
            return "%.3g%s" % (v / mult, unit)
    return "%.3gfs" % (v / 1e-15)


def _fmt_speed(stats) -> str:
    """Simulation speed: simulated time covered per wall-clock second.

    Rendered the way simulators themselves report it ('87us/s') rather than as
    a bare ratio -- 8.7e-05 says nothing at a glance, '87us/s' says the run
    covers 87 microseconds of design time every second.
    """
    v = stats.get("sim_speed_s_per_s")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        simtime, wall = stats.get("simtime_s"), stats.get("walltime_s")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0
                   for x in (simtime, wall)):
            return ""
        v = simtime / wall
    return "%s/s" % _eng_secs(v)


def _case_row(case):
    name = str(getattr(case, "name", "") or getattr(case, "testname", "") or "?")
    status = str(getattr(case, "status", "") or
                 ("pass" if getattr(case, "passed", False) else "fail"))
    view = str(getattr(case, "view", "") or getattr(case, "sim", "") or "")
    if view in ("unset", "none", "None"):
        # A producer's placeholder for "not recorded"; showing it as a column
        # value reads as a real backend name.
        view = ""
    errors = int(getattr(case, "errors", 0) or 0)
    stats = _stats(case)
    # Prefer the case's own walltime field; fall back to the stats map.
    walltime = getattr(case, "walltime_s", None)
    if not isinstance(walltime, (int, float)) or isinstance(walltime, bool):
        walltime = stats.get("walltime_s")
    return (name, view, status, (str(errors) if errors else ""),
            _fmt_simtime(stats), _fmt_secs(walltime), _fmt_speed(stats),
            _fmt_mem(stats))


def _has_tests(node) -> bool:
    if "std.TestResult" in node.types or "std.SuiteResult" in node.types:
        return True
    return any(_has_tests(c) for c in node.children)


def _results_panel(ctxt, rf):
    """The test report from the run record: the count headline, then at
    `normal` the failures (path, headline, failing checks, log line) and at
    `full` the whole tree after the generic task summary."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text
    from ..results.render_text import render_failures, render_tree, STATUS_WORD
    from ..tui_theme import S_LABEL

    level = _detail_level(ctxt)
    c = rf.summary.counts
    total = c.get("total", 0)
    headline = "%d/%d passed" % (c.get("pass", 0), total)
    for k, word in (("fail", "failed"), ("error", "errored"), ("timeout", "timed out"),
                    ("notrun", "not run")):
        if c.get(k):
            headline += ", %d %s" % (c[k], word)

    if level == FULL:
        body = Text(render_tree(rf, expand=True).rstrip("\n"))
    elif level == NORMAL and rf.summary.failures:
        # The first line of render_failures repeats the headline
        body = Text(render_failures(rf).split("\n", 1)[1].strip("\n"))
    else:
        body = "[%s]%s[/%s]" % (S_LABEL, rf.summary.msg or (
            "all cases passed" if total else "no tests ran"), S_LABEL)

    style = "green" if rf.summary.status == "pass" else "red"
    panel = Panel(body, title="Tests (%s)" % headline, border_style=style)
    if level == FULL:
        return Group(ctxt.task_summary(), panel)
    return panel


def test_summary(ctxt):
    """`summary:` callable. Returns a rich renderable, or None when the run
    produced no verdicts at all (nothing to report is not an error here -- the
    *gate* decides that, and a summary must never change the verdict)."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table

    from ..tui_theme import S_LABEL, S_SECONDARY

    rf = getattr(ctxt, "results", None)
    if rf is not None and _has_tests(rf.result):
        return _results_panel(ctxt, rf)

    # No run record (or no test results in it): the duck-typed path, kept for
    # one release.
    _log.debug("test_summary: no run record with test results; using the "
               "duck-typed output scan (deprecated)")
    cases, rollups = collect_cases(list(ctxt.output))
    if not cases and not rollups:
        return ctxt.task_summary()

    level = _detail_level(ctxt)
    total, passed, failed, errored = tally(cases, rollups)

    headline = "%d/%d passed" % (passed, total)
    if failed:
        headline += ", %d failed" % failed
    if errored:
        headline += ", %d errored" % errored

    blocks = []
    shown = cases if level == FULL else [
        c for c in cases if not getattr(c, "passed", False)]

    if shown and level != QUIET:
        rows = [(case, _case_row(case)) for case in shown]
        # Resource columns appear only when some case actually reported them:
        # a lint or formal producer publishes no stats, and empty columns are
        # just noise. Index into _case_row's tuple:
        #   4=simtime 5=wall 6=speed 7=memory
        _COLS = (4, 5, 6, 7)
        has = {i: any(r[i] for _c, r in rows) for i in _COLS}
        cols = [i for i in _COLS if has[i]]
        labels = {4: "simtime", 5: "wall", 6: "speed", 7: "peak-mem"}

        table = Table.grid(padding=(0, 2))
        for _ in range(4 + len(cols)):
            table.add_column(justify="left")
        if cols:
            # Unlabeled durations and sizes side by side are ambiguous; a
            # header costs one line and removes the guessing. It is read, so it
            # gets a named colour rather than `dim` -- see tui_theme.
            table.add_row("", "", "", "",
                          *["[%s]%s[/%s]" % (S_LABEL, labels[i], S_LABEL)
                            for i in cols])
        for case, r in rows:
            name, view, status, errors = r[0], r[1], r[2], r[3]
            style = "green" if getattr(case, "passed", False) else "red"
            table.add_row(
                "[%s]%s[/%s]" % (style, status, style),
                name.replace("[", "\\["), view, errors,
                # Resource figures are data: the column and its header already
                # place them below the verdict, so they need no dimming.
                *["[%s]%s[/%s]" % (S_SECONDARY, r[i], S_SECONDARY) if r[i]
                  else "" for i in cols])
        blocks.append(table)

    if not blocks:
        # The panel's only content -- the verdict itself.
        blocks.append("[%s]%s[/%s]" % (
            S_LABEL, "all cases passed" if total else "no tests ran", S_LABEL))

    style = "green" if (total and not failed and not errored) else "red"
    panel = Panel(Group(*blocks), title="Tests (%s)" % headline,
                  border_style=style)

    if level == FULL:
        return Group(ctxt.task_summary(), panel)
    return panel
