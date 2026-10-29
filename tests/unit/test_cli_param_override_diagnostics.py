"""
Diagnostics for `-D` parameter overrides that bind nowhere, or bind in two
namespaces at once. Binding semantics are unchanged -- these are warnings only.
"""
import textwrap

import pytest

from dv_flow.mgr.cmds.cmd_run import CmdRun
from dv_flow.mgr.param_override_tracker import OverrideBindingTracker
from dv_flow.mgr.util import parameter_override_keys


class Args:
    """Minimal args holder for CmdRun"""
    def __init__(self, root, tasks=None, defines=None, param_file=None,
                 strict_params=False):
        self.param_file = param_file
        self.strict_params = strict_params
        self.tasks = tasks if tasks is not None else []
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = defines if defines is not None else []
        self.config = None
        self.root = root


FLOW = textwrap.dedent('''\
package:
  name: my_pkg
  with:
    pkg_var:
      type: str
      value: "default"
  tasks:
  - name: entry
    scope: root
    desc: "Entry point"
    with:
      top:
        type: str
        value: "orig"
    run: echo "entry ${{ top }}"
''')


def _run(tmp_path, monkeypatch, capsys, defines, tasks=('entry',),
         flow=FLOW, param_file=None):
    (tmp_path / 'flow.yaml').write_text(flow)
    monkeypatch.chdir(tmp_path)
    CmdRun()(Args(root=str(tmp_path), tasks=list(tasks), defines=defines,
                  param_file=param_file))
    return capsys.readouterr()


# ---------------------------------------------------------------------------
# parameter_override_keys
# ---------------------------------------------------------------------------

def test_override_keys_preserve_original_spelling():
    """The categorized dict rewrites keys; diagnostics need what was typed."""
    keys = parameter_override_keys(["top=x", "-Dmy_pkg.pkg_var=y", "a.b.c=z"])
    assert keys == ["top", "my_pkg.pkg_var", "a.b.c"]


def test_override_keys_skip_malformed_and_dedup():
    assert parameter_override_keys(["novalue", "=v", "a=1", "a=2"]) == ["a"]
    assert parameter_override_keys(None) == []


# ---------------------------------------------------------------------------
# OverrideBindingTracker
# ---------------------------------------------------------------------------

def test_tracker_reports_unmatched():
    t = OverrideBindingTracker(keys=["good", "typo"])
    t.note_task_bind("good", "my_pkg.entry")
    assert t.unmatched() == ["typo"]
    assert t.ambiguous() == []
    assert len(t.warnings()) == 1
    assert "typo" in t.warnings()[0]


def test_tracker_ignores_binds_for_untracked_keys():
    """-P param-file entries reach the same consumers but are not -D keys."""
    t = OverrideBindingTracker(keys=["a"])
    t.note_task_bind("from_param_file", "my_pkg.entry")
    assert t.unmatched() == ["a"]


def test_tracker_reports_ambiguity_with_qualified_suggestion():
    t = OverrideBindingTracker(keys=["seed"])
    t.note_package_bind("seed", "my_pkg")
    t.note_task_bind("seed", "my_pkg.entry")
    assert t.unmatched() == []
    assert t.ambiguous() == [("seed", ["my_pkg"], ["my_pkg.entry"])]
    msg = t.warnings()[0]
    # Both targets are named, and the qualified forms are suggested.
    assert "my_pkg" in msg and "my_pkg.entry" in msg
    assert "-D my_pkg.seed=" in msg
    assert "-D my_pkg.entry.seed=" in msg


def test_tracker_omits_suggestion_for_dotted_key():
    """`a.b` is already both `pkg a var b` and `task a param b` -- there is no
    more-specific form to suggest."""
    t = OverrideBindingTracker(keys=["a.b"])
    t.note_package_bind("a.b", "a")
    t.note_task_bind("a.b", "pkg.a")
    msg = t.warnings()[0]
    assert "ambiguous" in msg
    assert "Qualify it as" not in msg


# ---------------------------------------------------------------------------
# End-to-end through CmdRun
# ---------------------------------------------------------------------------

def test_unmatched_define_warns(tmp_path, monkeypatch, capsys):
    cap = _run(tmp_path, monkeypatch, capsys, ["nonexistent=1"])
    assert "nonexistent" in cap.err
    assert "matched no package variable or task parameter" in cap.err


def test_bad_param_on_in_graph_task_already_errors(tmp_path, monkeypatch, capsys):
    """Not a diagnostics gap: naming a real task and a bad param is already a
    hard error, which is stronger than a warning. Pinned so the new tracking
    code does not downgrade it."""
    cap = _run(tmp_path, monkeypatch, capsys, ["my_pkg.entry.badparam=1"])
    assert "Parameter 'badparam' not found in task 'my_pkg.entry'" in cap.err


def test_unmatched_task_name_warns(tmp_path, monkeypatch, capsys):
    """The real gap: a typo in the *task* name means the override is offered to
    a task that never exists, and today nothing is said."""
    cap = _run(tmp_path, monkeypatch, capsys, ["my_pkg.entrry.top=1"])
    assert "my_pkg.entrry.top" in cap.err
    assert "matched no package variable or task parameter" in cap.err


def test_matched_task_param_is_silent(tmp_path, monkeypatch, capsys):
    cap = _run(tmp_path, monkeypatch, capsys, ["top=hello"])
    assert "matched no package variable" not in cap.err


def test_matched_package_var_is_silent(tmp_path, monkeypatch, capsys):
    cap = _run(tmp_path, monkeypatch, capsys, ["pkg_var=hello"])
    assert "matched no package variable" not in cap.err


def test_exit_status_unchanged_by_unmatched_define(tmp_path, monkeypatch, capsys):
    """Diagnostics must not turn a passing run into a failure."""
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    ok = CmdRun()(Args(root=str(tmp_path), tasks=['entry'], defines=[]))
    capsys.readouterr()
    warned = CmdRun()(Args(root=str(tmp_path), tasks=['entry'], defines=["typo=1"]))
    assert warned == ok


def test_ambiguous_bare_key_warns_naming_both(tmp_path, monkeypatch, capsys):
    """A bare key that names both a package var and a task param binds BOTH
    (unchanged behavior) and is reported."""
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: my_pkg
      with:
        shared:
          type: str
          value: "pkg"
      tasks:
      - name: entry
        scope: root
        with:
          shared:
            type: str
            value: "task"
        run: echo "entry"
    '''))
    monkeypatch.chdir(tmp_path)
    CmdRun()(Args(root=str(tmp_path), tasks=['entry'], defines=["shared=x"]))
    err = capsys.readouterr().err
    assert "ambiguous" in err
    assert "my_pkg" in err


# ---------------------------------------------------------------------------
# -P param-file entries
# ---------------------------------------------------------------------------

# `entry` plus a root task that the run of `entry` never reaches.
FLOW_P = FLOW + textwrap.indent(textwrap.dedent('''\
- name: other
  scope: root
  with:
    mode:
      type: str
      value: "a"
  run: echo "other ${{ mode }}"
'''), '  ')


def _run_p(tmp_path, monkeypatch, capsys, data, defines=None):
    import json
    pf = tmp_path / 'params.json'
    pf.write_text(json.dumps(data))
    return _run(tmp_path, monkeypatch, capsys, defines or [],
                flow=FLOW_P, param_file=str(pf))


def test_tracker_param_file_warnings_classify():
    t = OverrideBindingTracker()
    t.add_param_file("p.json", {
        'package': {'nope': 1},
        'task': {'bogus': {'x': 1}, 'other': {'mode': 'b', 'typo': 1}}})
    params = {'other': {'mode'}}
    msgs = t.param_file_warnings(lambda k: params.get(k))
    assert len(msgs) == 4
    assert "p.json: package.nope" in msgs[0]
    assert "matched no package variable" in msgs[0]
    assert "unknown task 'bogus'" in msgs[1]
    assert "p.json: tasks.bogus.x" in msgs[1]
    assert "never entered the graph" in msgs[2]
    assert "'dfm show task other'" in msgs[2]
    assert "no parameter 'typo'" in msgs[3] and "'other'" in msgs[3]


def test_bad_param_file_warns_per_unknown_task_and_runs(tmp_path, monkeypatch, capsys):
    cap = _run_p(tmp_path, monkeypatch, capsys, {'tasks': {
        'entrry': {'top': 'x'}, 'bld': {'top': 'y'}}})
    assert cap.err.count("unknown task") == 2
    assert "tasks.entrry.top" in cap.err and "tasks.bld.top" in cap.err
    assert "dfm show task" in cap.err
    # The run still goes ahead.
    assert "Done: 1" in cap.out


def test_correct_param_file_is_silent(tmp_path, monkeypatch, capsys):
    cap = _run_p(tmp_path, monkeypatch, capsys, {
        'package': {'pkg_var': 'v'}, 'tasks': {'entry': {'top': 'hello'}}})
    assert "-P entry" not in cap.err


def test_param_file_unknown_param_names_task_and_param(tmp_path, monkeypatch, capsys):
    cap = _run_p(tmp_path, monkeypatch, capsys, {'tasks': {
        'other': {'mod': 'b'}}})
    assert "task 'other' has no parameter 'mod'" in cap.err


def test_param_file_task_outside_graph_warns(tmp_path, monkeypatch, capsys):
    cap = _run_p(tmp_path, monkeypatch, capsys, {'tasks': {
        'other': {'mode': 'b'}}})
    assert "task 'other' never entered the graph" in cap.err


def test_param_file_entry_shadowed_by_define_is_silent(tmp_path, monkeypatch, capsys):
    cap = _run_p(tmp_path, monkeypatch, capsys,
                 {'tasks': {'entry': {'top': 'p'}}}, defines=["entry.top=d"])
    assert "-P entry" not in cap.err


# ---------------------------------------------------------------------------
# strict mode: --strict-params / DFM_STRICT_PARAMS=1
# ---------------------------------------------------------------------------

def _run_strict(tmp_path, monkeypatch, capsys, data, strict=True, defines=None):
    import json
    (tmp_path / 'flow.yaml').write_text(FLOW_P)
    pf = tmp_path / 'params.json'
    pf.write_text(json.dumps(data))
    monkeypatch.chdir(tmp_path)
    rc = CmdRun()(Args(root=str(tmp_path), tasks=['entry'],
                       defines=defines or [], param_file=str(pf),
                       strict_params=strict))
    return rc, capsys.readouterr()


def test_strict_bad_param_file_exits_before_running(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('DFM_STRICT_PARAMS', raising=False)
    rc, cap = _run_strict(tmp_path, monkeypatch, capsys, {'tasks': {
        'entrry': {'top': 'x'}}})
    assert rc == 1
    assert "Error: " in cap.err and "unknown task 'entrry'" in cap.err
    assert "strict mode" in cap.err
    assert "Done: 1" not in cap.out


def test_strict_unmatched_define_exits(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('DFM_STRICT_PARAMS', raising=False)
    rc, cap = _run_strict(tmp_path, monkeypatch, capsys, {},
                          defines=["no_such_key=1"])
    assert rc == 1
    assert "no_such_key" in cap.err
    assert "Done: 1" not in cap.out


def test_strict_via_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('DFM_STRICT_PARAMS', '1')
    rc, cap = _run_strict(tmp_path, monkeypatch, capsys, {'tasks': {
        'entrry': {'top': 'x'}}}, strict=False)
    assert rc == 1
    assert "strict mode" in cap.err
    assert "Done: 1" not in cap.out


def test_strict_correct_param_file_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('DFM_STRICT_PARAMS', raising=False)
    rc, cap = _run_strict(tmp_path, monkeypatch, capsys, {
        'package': {'pkg_var': 'v'}, 'tasks': {'entry': {'top': 'hello'}}})
    assert rc == 0
    assert "strict mode" not in cap.err
    assert "Done: 1" in cap.out


def test_strict_cli_flag_parses():
    from dv_flow.mgr.__main__ import get_parser
    args = get_parser().parse_args(['run', '--strict-params', 'entry'])
    assert args.strict_params is True
    args = get_parser().parse_args(['run', 'entry'])
    assert args.strict_params is False
