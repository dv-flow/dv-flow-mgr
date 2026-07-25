"""
`dfm run` -- the single-task front-end. `run` takes exactly one task, which is
what makes the per-task front-end behavior (task argument parsing, `--help`
rendering the task's arguments, a task-declared `summary:`) well defined.

These tests pin the parser shape and the `task` -> `tasks` normalization inside
CmdRun; the task-argument parsing itself lives in test_task_cli_args.py.
"""
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr.__main__ import get_parser, _add_run_opts, reserved_option_strings
from dv_flow.mgr.cmds.cmd_run import CmdRun


FLOW = textwrap.dedent('''\
package:
  name: my_pkg
  tasks:
  - name: entry
    scope: root
    desc: "Entry point"
    run: echo "hello from entry"
  - name: helper
    desc: "Not root"
    run: echo "helper"
''')


def _subparser(parser, name):
    for action in parser._subparsers._group_actions:
        if name in getattr(action, 'choices', {}):
            return action.choices[name]
    raise AssertionError("no such subcommand: %s" % name)


# ---------------------------------------------------------------------------
# Parser shape
# ---------------------------------------------------------------------------

def test_run_accepts_a_single_task():
    args = get_parser().parse_args(["run", "entry"])
    assert args.task == "entry"


def test_run_accepts_no_task():
    assert get_parser().parse_args(["run"]).task is None


def test_run_takes_exactly_one_task():
    """A second positional is not a second task. Since task arguments are
    accepted bare, it becomes a *task argument*, which the task's own parser
    rejects in phase 2 (see test_task_cli_args.py). Under plain `parse_args` --
    no phase 2 to hand it to -- it is still a hard error."""
    with pytest.raises(SystemExit):
        get_parser().parse_args(["run", "entry", "other"])
    args, extra = get_parser().parse_known_args(["run", "entry", "other"])
    assert args.task == "entry" and extra == ["other"]


def test_exec_is_gone():
    """`exec` was folded back into `run`; it is not a subcommand any more."""
    with pytest.raises(SystemExit):
        get_parser().parse_args(["exec", "entry"])


@pytest.mark.parametrize("opt,value", [
    ("-j", "2"),
    ("--clean", None),
    ("--base-rundir", "/tmp"),
    ("-f", None),
    ("--force", None),
    ("-v", None),
    ("--verbose", None),
    ("--root", "/tmp"),
    ("-c", "cfg"),
    ("--config", "cfg"),
    ("-u", "log"),
    ("--ui", "log"),
    ("-D", "a=1"),
    ("-P", "{}"),
    ("--param-file", "{}"),
    ("--runner", "local"),
    ("--runner-opt", "k=v"),
    ("--override", "a=b"),
    ("--report", "/tmp/r"),
    ("--run-id", "0001"),
])
def test_every_run_option_is_still_accepted(opt, value):
    argv = ["run", "entry", opt] + ([value] if value is not None else [])
    args = get_parser().parse_args(argv)
    assert args.task == "entry"


# ---------------------------------------------------------------------------
# reserved_option_strings
# ---------------------------------------------------------------------------

def test_reserved_option_strings_covers_run_and_global():
    parser = get_parser()
    reserved = reserved_option_strings(parser, _subparser(parser, "run"))
    for opt in ("-h", "--help", "--log-level", "-D", "--clean", "-j",
                "--report", "--run-id", "--base-rundir"):
        assert opt in reserved, opt
    # Positionals contribute nothing.
    assert "task" not in reserved


def test_reserved_option_strings_tracks_new_options():
    """Derived, not hand-listed: a newly added option shows up automatically."""
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    before = reserved_option_strings(p)
    p.add_argument("--brand-new", action="store_true")
    assert reserved_option_strings(p) - before == {"--brand-new"}


# ---------------------------------------------------------------------------
# Execution equivalence
# ---------------------------------------------------------------------------

class Args:
    """Minimal args holder. Mirrors what argparse produces for `run` (a `task`
    attribute and no `tasks`); a pre-set `tasks` list stands in for the other
    entry points that supply roots directly."""
    def __init__(self, root, **kw):
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root
        for k, v in kw.items():
            setattr(self, k, v)


def test_run_normalizes_task_to_tasks(tmp_path, monkeypatch, capsys):
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    args = Args(root=str(tmp_path), task='entry')
    CmdRun()(args)
    assert args.tasks == ['my_pkg.entry'] or args.tasks == ['entry']


def test_task_and_tasks_produce_the_same_status(tmp_path, monkeypatch, capsys):
    """The normalization is the only difference: a pre-set `tasks` list and a
    single `task` reach the same runner and the same status."""
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    list_status = CmdRun()(Args(root=str(tmp_path), tasks=['entry']))
    capsys.readouterr()
    task_status = CmdRun()(Args(root=str(tmp_path), task='entry'))
    capsys.readouterr()
    assert task_status == list_status == 0


def test_run_resolves_a_partial_task_name(tmp_path, monkeypatch, capsys):
    """`run` resolves its task through CLITaskResolver."""
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    # 'entry' is the leaf of 'my_pkg.entry'
    assert CmdRun()(Args(root=str(tmp_path), task='entry')) == 0
    capsys.readouterr()
    assert CmdRun()(Args(root=str(tmp_path), task='my_pkg.entry')) == 0


# ---------------------------------------------------------------------------
# Client mode (DFM_SERVER_SOCKET)
# ---------------------------------------------------------------------------

class _FakeClient:
    """Stands in for DfmClient. Records what the client-mode branch forwarded."""
    calls = None

    def __init__(self, socket_path):
        pass

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def run(self, tasks, param_overrides, timeout):
        _FakeClient.calls = (tasks, param_overrides, timeout)
        return {"status": 0}


@pytest.fixture
def fake_client(monkeypatch):
    from dv_flow.mgr import dfm_server
    _FakeClient.calls = None
    monkeypatch.setattr(dfm_server, "DfmClient", _FakeClient)
    return _FakeClient


def _client_mode(monkeypatch, argv):
    from dv_flow.mgr.__main__ import _run_client_mode
    monkeypatch.setattr(sys, "argv", ["dfm"] + argv)
    return _run_client_mode("/nonexistent.sock")


def test_client_mode_forwards_run(monkeypatch, fake_client, capsys):
    """DFM_SERVER_SOCKET is set inside an Agent task, so this is the path agents
    take."""
    rc = _client_mode(monkeypatch, ["run", "entry", "-D", "top=x"])
    assert rc == 0
    assert fake_client.calls == (["entry"], {"top": "x"}, None)


def test_client_mode_rejects_extra_tokens(monkeypatch, fake_client, capsys):
    """Task arguments cannot cross the protocol yet, so say so rather than
    silently running the extra token as a second task."""
    rc = _client_mode(monkeypatch, ["run", "entry", "extra"])
    assert rc == 1
    assert fake_client.calls is None
    assert "takes one task" in capsys.readouterr().err


def test_run_with_no_task_lists_root_tasks(tmp_path, monkeypatch, capsys):
    """A bare `dfm run` lists the root tasks."""
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    CmdRun()(Args(root=str(tmp_path), task=None))
    out = capsys.readouterr().out
    assert 'Available Tasks:' in out
    assert 'my_pkg.entry' in out
    assert 'my_pkg.helper' not in out
