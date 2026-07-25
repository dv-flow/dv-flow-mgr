"""
The end-of-run summary: the `task-summary` builtin over the node graph, the
`summary:` task capability, and file/bundle output.
"""
import datetime
import json
import os
import textwrap

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.cmds.cmd_run import CmdRun
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE
from dv_flow.mgr.task_node import TaskNode
from dv_flow.mgr import summary_builtin as sb
from dv_flow.mgr.summary_ctxt import (
    SummaryCtxt, resolve_task_summary, invoke_summary, summary_file_text,
    is_builtin_summary, BUILTIN_TASK_SUMMARY)
from dv_flow.mgr.util import loadProjPkgDef


# ---------------------------------------------------------------------------
# Synthetic nodes -- exercise classification without running a flow
# ---------------------------------------------------------------------------

def _node(name, status=0, changed=True, cache_hit=False, base_hit=False,
          markers=None, elapsed=None, result=True):
    n = TaskNode(name=name, srcdir=".", params=None, ctxt=None)
    if result:
        n.result = TaskDataResult(status=status, changed=changed,
                                  cache_hit=cache_hit, base_hit=base_hit,
                                  markers=markers or [])
    if elapsed is not None:
        n.start = datetime.datetime(2020, 1, 1)
        n.end = n.start + datetime.timedelta(seconds=elapsed)
    return n


def _chain(*nodes):
    """Wire nodes into a linear needs-chain: nodes[i] needs nodes[i-1]."""
    for prev, cur in zip(nodes, nodes[1:]):
        cur.needs.append((prev, False))
    return nodes[-1]


def test_classification_of_each_status():
    err = _node("err", status=1)
    warn = _node("warn", markers=[TaskMarker(msg="m", severity=SeverityE.Warning)])
    cache = _node("cache", cache_hit=True)
    base = _node("base", base_hit=True)
    uptodate = _node("uptodate", changed=False)
    done = _node("done")
    unknown = _node("unknown", result=False)
    root = _chain(err, warn, cache, base, uptodate, done, unknown)

    got = {f.name: f.status for f in sb.collect_task_facts(root)}
    assert got == {
        'err': sb.ERROR, 'warn': sb.WARNING, 'cache': sb.CACHE_HIT,
        'base': sb.BASE_HIT, 'uptodate': sb.UPTODATE, 'done': sb.DONE,
        'unknown': sb.UNKNOWN,
    }


def test_error_beats_cache_hit():
    """A failing cache hit is still a failure -- order of tests matters."""
    n = _node("t", status=1, cache_hit=True)
    assert sb.collect_task_facts(n)[0].status == sb.ERROR


def test_error_marker_without_nonzero_status_is_an_error():
    n = _node("t", status=0, markers=[TaskMarker(msg="bad", severity=SeverityE.Error)])
    assert sb.collect_task_facts(n)[0].status == sb.ERROR


def test_counts_match_a_known_mix():
    root = _chain(_node("a"), _node("b", changed=False), _node("c", status=1),
                  _node("d", cache_hit=True))
    counts = sb.count_facts(sb.collect_task_facts(root))
    assert counts['total'] == 4
    assert counts[sb.DONE] == 1
    assert counts[sb.UPTODATE] == 1
    assert counts[sb.ERROR] == 1
    assert counts[sb.CACHE_HIT] == 1


def test_title_omits_zero_counts_and_shows_cache_only_when_enabled():
    counts = sb.count_facts(sb.collect_task_facts(_node("a")))
    assert sb.summary_title(counts) == "Total: 1 | Done: 1"
    assert "Cache: 0 hit / 1 miss" in sb.summary_title(counts, cache_enabled=True)


def test_nodes_are_in_dependency_order():
    a, b, c = _node("a"), _node("b"), _node("c")
    root = _chain(a, b, c)
    assert [n.name for n in sb.ordered_nodes(root)] == ["a", "b", "c"]


def test_ordering_is_deterministic_across_calls():
    """--summary-file depends on this: two runs of the same graph must render
    identically."""
    root = _chain(_node("z"), _node("y"), _node("x"))
    assert sb.render_task_summary_text(root) == sb.render_task_summary_text(root)


def test_quiet_statuses_are_hidden_unless_verbose():
    root = _chain(_node("ran"), _node("quiet", changed=False))
    assert "quiet" not in sb.render_task_summary_text(root)
    assert "quiet" in sb.render_task_summary_text(root, verbose=True)
    # ...but the count still includes it.
    assert "Up-to-date: 1" in sb.render_task_summary_text(root)


def test_a_quiet_task_with_markers_is_still_shown():
    n = _node("quiet", changed=False,
              markers=[TaskMarker(msg="note", severity=SeverityE.Info)])
    assert "quiet" in sb.render_task_summary_text(n)


def test_text_render_has_no_ansi_and_includes_markers():
    n = _node("t", markers=[TaskMarker(msg="boom", severity=SeverityE.Error)])
    text = sb.render_task_summary_text(n)
    assert '\x1b[' not in text
    assert 'boom' in text


def test_markdown_render_is_real_markdown():
    n = _node("t", elapsed=2.0,
              markers=[TaskMarker(msg="boom", severity=SeverityE.Error)])
    md = sb.render_task_summary_markdown(n)
    assert md.startswith("## Task Summary")
    assert "| Status | Task | Time |" in md
    assert "`t`" in md
    assert "### Markers" in md
    assert "boom" in md
    # Not a fenced block of box drawing.
    assert "```" not in md
    assert "│" not in md


def test_elapsed_formatting():
    assert sb.format_elapsed(None) == ""
    assert sb.format_elapsed(2.0) == "2.00s"
    assert sb.format_elapsed(0.5) == "500.00ms"


def test_dep_map_includes_compound_subtasks():
    parent = _node("parent")
    sub = _node("sub")
    parent.tasks = [sub, parent]   # compound nodes list themselves
    assert sub in sb.dep_map(parent)[parent]
    assert {n.name for n in sb.ordered_nodes(parent)} == {"parent", "sub"}


def test_result_none_falls_back_to_disk(tmp_path):
    """The inverse of TaskListenerReport: memory first, disk only as fallback."""
    n = _node("t", result=False)
    n.rundir = [str(tmp_path)]
    with open(tmp_path / "exec_data.json", "w") as f:
        json.dump({"status": 1, "markers": [
            {"severity": "error", "msg": "from disk"}]}, f)
    facts = sb.collect_task_facts(n)
    assert facts[0].status == sb.ERROR
    assert "from disk" in sb.render_task_summary_text(n)


# ---------------------------------------------------------------------------
# SummaryCtxt / resolution
# ---------------------------------------------------------------------------

def _ctxt(root, status=0, **kw):
    return SummaryCtxt(root=root, status=status, roots=[root], **kw)


def test_ctxt_tasks_pairs_nodes_with_results():
    root = _chain(_node("a"), _node("b"))
    pairs = _ctxt(root).tasks
    assert [n.name for n, _ in pairs] == ["a", "b"]
    assert all(r is not None for _, r in pairs)


def test_ctxt_markers_are_flattened():
    root = _chain(_node("a", markers=[TaskMarker(msg="one", severity=SeverityE.Info)]),
                  _node("b", markers=[TaskMarker(msg="two", severity=SeverityE.Info)]))
    assert [m.msg for m in _ctxt(root).markers()] == ["one", "two"]


def test_ctxt_task_summary_returns_the_builtin_renderable():
    panel = _ctxt(_node("a")).task_summary()
    assert "Task Summary" in str(getattr(panel, 'title', ''))


def test_invoke_builtin_by_name_and_by_dict():
    ctxt = _ctxt(_node("a"))
    assert invoke_summary(BUILTIN_TASK_SUMMARY, ctxt) is not None
    assert invoke_summary({'builtin': 'task-summary'}, ctxt) is not None
    assert is_builtin_summary({'builtin': 'task-summary'})
    assert not is_builtin_summary("mod:fn")


def test_unknown_builtin_is_reported_not_raised():
    assert invoke_summary({'builtin': 'nope'}, _ctxt(_node("a"))) is None


def test_unimportable_summary_is_reported_not_raised():
    assert invoke_summary("no.such.module:fn", _ctxt(_node("a"))) is None


# Module-level summary callables, referenced by `summary:` in the flows below.
def summary_str(summary):
    return "STR-SUMMARY status=%d tasks=%d" % (summary.status, len(summary.tasks))


def summary_renderable(summary):
    return summary.task_summary()


def summary_none(summary):
    return None


def summary_boom(summary):
    raise RuntimeError("summary exploded")


def test_callable_summary_return_types():
    ctxt = _ctxt(_node("a"))
    ref = "%s:%%s" % __name__
    assert invoke_summary(ref % "summary_str", ctxt).startswith("STR-SUMMARY")
    assert invoke_summary(ref % "summary_renderable", ctxt) is not None
    assert invoke_summary(ref % "summary_none", ctxt) is None


def test_a_raising_summary_is_swallowed():
    assert invoke_summary("%s:summary_boom" % __name__, _ctxt(_node("a"))) is None


# ---------------------------------------------------------------------------
# summary_file_text
# ---------------------------------------------------------------------------

def test_file_text_for_builtin_picks_format_by_flag():
    ctxt = _ctxt(_node("a"))
    md = summary_file_text(BUILTIN_TASK_SUMMARY, ctxt, None, markdown=True)
    txt = summary_file_text(BUILTIN_TASK_SUMMARY, ctxt, None, markdown=False)
    assert md.startswith("## Task Summary")
    assert txt.startswith("Task Summary (")


def test_file_text_passes_a_string_through():
    ctxt = _ctxt(_node("a"))
    assert summary_file_text("mod:fn", ctxt, "hello", markdown=True) == "hello\n"


def test_file_text_fences_a_renderable_for_markdown():
    ctxt = _ctxt(_node("a"))
    value = ctxt.task_summary()
    md = summary_file_text("mod:fn", ctxt, value, markdown=True)
    txt = summary_file_text("mod:fn", ctxt, value, markdown=False)
    assert md.startswith("```") and md.rstrip().endswith("```")
    assert not txt.startswith("```")
    assert '\x1b[' not in md and '\x1b[' not in txt


def test_file_text_is_none_for_a_none_summary():
    assert summary_file_text("mod:fn", _ctxt(_node("a")), None) is None


def test_renderable_file_text_is_width_stable():
    """Fixed width, not the terminal's -- otherwise local and CI bytes differ."""
    ctxt = _ctxt(_node("a-very-long-task-name-that-would-wrap-narrow-terminals"))
    a = summary_file_text("mod:fn", ctxt, ctxt.task_summary())
    b = summary_file_text("mod:fn", ctxt, ctxt.task_summary())
    assert a == b
    assert max(len(l) for l in a.splitlines()) <= 100


# ---------------------------------------------------------------------------
# End-to-end through CmdRun
# ---------------------------------------------------------------------------

FLOW = textwrap.dedent('''\
package:
  name: p
  tasks:
  - name: entry
    scope: root
    run: echo "entry"
''')


class Args:
    def __init__(self, root, **kw):
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root
        # `tasks` is deliberately NOT preset: CmdRun keys single-root mode off
        # its absence, so presetting it would silently disable task-arg parsing.
        for k, v in kw.items():
            setattr(self, k, v)


def _write(tmp_path, monkeypatch, flow=FLOW):
    (tmp_path / 'flow.yaml').write_text(flow)
    monkeypatch.chdir(tmp_path)


def test_summary_appears_with_log_ui(tmp_path, monkeypatch, capsys):
    """The whole point: piped/CI runs used to get nothing."""
    _write(tmp_path, monkeypatch)
    CmdRun()(Args(str(tmp_path), tasks=['entry'], ui='log'))
    assert 'Task Summary' in capsys.readouterr().out


def test_summary_is_printed_once_under_progress_ui(tmp_path, monkeypatch, capsys):
    """The listener used to print its own panel; it now delegates."""
    _write(tmp_path, monkeypatch)
    CmdRun()(Args(str(tmp_path), tasks=['entry'], ui='progress'))
    assert capsys.readouterr().out.count('Task Summary') == 1


def test_no_summary_silences_the_console(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch)
    CmdRun()(Args(str(tmp_path), tasks=['entry'], no_summary=True))
    assert 'Task Summary' not in capsys.readouterr().out


def test_summary_file_is_written_even_with_no_summary(tmp_path, monkeypatch, capsys):
    """'Silence the console, write the file' is a real CI configuration."""
    _write(tmp_path, monkeypatch)
    out = tmp_path / "s.md"
    CmdRun()(Args(str(tmp_path), tasks=['entry'], no_summary=True,
                  summary_file=str(out)))
    assert 'Task Summary' not in capsys.readouterr().out
    assert out.read_text().startswith("## Task Summary")


def test_summary_file_format_follows_extension(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch)
    md, txt = tmp_path / "s.md", tmp_path / "s.txt"
    CmdRun()(Args(str(tmp_path), tasks=['entry'], summary_file=str(md)))
    CmdRun()(Args(str(tmp_path), tasks=['entry'], summary_file=str(txt)))
    capsys.readouterr()
    assert md.read_text().startswith("## Task Summary")
    assert txt.read_text().startswith("Task Summary (")


def test_summary_file_is_byte_identical_across_runs(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch)
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    CmdRun()(Args(str(tmp_path), tasks=['entry'], summary_file=str(a), force=True))
    CmdRun()(Args(str(tmp_path), tasks=['entry'], summary_file=str(b), force=True))
    capsys.readouterr()
    # Timings differ run to run; compare everything else.
    strip = lambda s: "\n".join(l.split("  ")[0] for l in s.splitlines())
    assert strip(a.read_text()) == strip(b.read_text())


def test_declared_summary_is_used_for_the_invoked_root(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary: %s:summary_str
        run: echo "entry"
    ''') % __name__)
    CmdRun()(Args(str(tmp_path), task='entry'))
    assert 'STR-SUMMARY' in capsys.readouterr().out


def test_declared_summary_is_used_under_run_with_one_task(tmp_path, monkeypatch, capsys):
    """A declared summary belongs to a *single invoked root* -- that is the
    whole condition, and `dfm run <one-task>` satisfies it.

    This previously also required `run`, by testing `args.task` (which only the
    `run` parser defines; `run` has `args.tasks`). The effect was invisible
    until a flow declared `summary:`, and then `dfm run tests` quietly rendered
    the generic panel while `dfm run tests` rendered the task's own report.
    Since `run <task>` is what people type, the gate is now the single-root
    condition alone."""
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary: %s:summary_str
        run: echo "entry"
    ''') % __name__)
    CmdRun()(Args(str(tmp_path), tasks=['entry']))
    assert 'STR-SUMMARY' in capsys.readouterr().out


def test_declared_summary_is_inert_with_several_roots(tmp_path, monkeypatch, capsys):
    """With more than one invoked root there is no single declaration to
    honor, so the builtin is used -- the condition the `run` gate was standing
    in for."""
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary: %s:summary_str
        run: echo "entry"
      - name: other
        scope: root
        run: echo "other"
    ''') % __name__)
    CmdRun()(Args(str(tmp_path), tasks=['entry', 'other']))
    out = capsys.readouterr().out
    assert 'STR-SUMMARY' not in out
    assert 'Task Summary' in out


def test_summary_is_inherited_nearest_wins(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: base
        summary: a:one
      - name: mid
        uses: base
      - name: derived
        uses: mid
        summary: b:two
    '''))
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert resolve_task_summary(pkg.task_m['p.mid']) == 'a:one'
    assert resolve_task_summary(pkg.task_m['p.derived']) == 'b:two'
    assert resolve_task_summary(pkg.task_m['p.base']) == 'a:one'


def test_builtin_form_parses_from_yaml(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary:
          builtin: task-summary
        run: echo entry
    '''))
    loader, pkg = loadProjPkgDef(str(tmp_path))
    decl = resolve_task_summary(pkg.task_m['p.entry'])
    assert is_builtin_summary(decl)


def test_a_raising_summary_does_not_change_status(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary: %s:summary_boom
        run: echo "entry"
    ''') % __name__)
    assert CmdRun()(Args(str(tmp_path), task='entry')) == 0


def test_a_none_summary_writes_no_file(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: entry
        scope: root
        summary: %s:summary_none
        run: echo "entry"
    ''') % __name__)
    out = tmp_path / "s.md"
    CmdRun()(Args(str(tmp_path), task='entry', summary_file=str(out)))
    capsys.readouterr()
    assert not out.exists()


# ---------------------------------------------------------------------------
# --report bundle integration
# ---------------------------------------------------------------------------

def test_report_bundle_gets_summary_md(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch)
    rep = tmp_path / "rep"
    CmdRun()(Args(str(tmp_path), tasks=['entry'], report_dir=str(rep)))
    capsys.readouterr()
    assert (rep / "summary.md").read_text().startswith("## Task Summary")
    report_md = (rep / "report.md").read_text()
    assert "# DV Flow Run Report" in report_md
    assert "## Task Summary" in report_md
    # The metadata bullet list stays intact -- the summary follows it.
    assert report_md.index("- **Result:**") < report_md.index("## Task Summary")


def test_report_without_summary_is_unchanged(tmp_path, monkeypatch, capsys):
    """`--report` alone must keep working exactly as before."""
    from dv_flow.mgr.task_listener_report import TaskListenerReport
    rep = tmp_path / "rep"
    rep.mkdir()
    r = TaskListenerReport(rundir=str(tmp_path), root_name="p")
    r.generate(str(rep), generated_unix=0)
    assert not (rep / "summary.md").exists()
    assert "## Task Summary" not in (rep / "report.md").read_text()


def test_report_and_summary_file_together(tmp_path, monkeypatch, capsys):
    _write(tmp_path, monkeypatch)
    rep, sfile = tmp_path / "rep", tmp_path / "s.md"
    CmdRun()(Args(str(tmp_path), tasks=['entry'], report_dir=str(rep),
                  summary_file=str(sfile)))
    capsys.readouterr()
    assert sfile.exists() and (rep / "summary.md").exists()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_summary_flags_on_run():
    argv = ["run", "entry", "--no-summary", "--summary-file", "s.md"]
    args = get_parser().parse_args(argv)
    assert args.no_summary is True
    assert args.summary_file == "s.md"


def test_summary_flags_default_off():
    args = get_parser().parse_args(["run", "entry"])
    assert args.no_summary is False
    assert args.summary_file is None
