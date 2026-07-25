"""
Task-declared command-line arguments: the `cli:` block, its load-time
validation, the two-phase `run` parse, and how parsed values bind to params.
"""
import json
import textwrap

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.cli_args import (
    resolve_task_cli, reserved_options, build_arg_parser, parse_task_args,
    validate_task_cli)
from dv_flow.mgr.cmds.cmd_run import CmdRun
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


FLOW = textwrap.dedent('''\
package:
  name: t
  tasks:
  - name: run-tests
    scope: root
    desc: Run the UVM regression suite
    cli:
      args:
      - name: seed
        short: s
      - name: count
      - name: sim
        choices: [vlt, vcs, xsim]
    with:
      seed: { type: int, value: 0, doc: Base random seed }
      count: { type: int, value: 10, doc: Number of iterations }
      sim: { type: str, value: vlt, doc: Simulator backend }
    run: echo hello
  - name: plain
    scope: root
    with:
      seed: { type: int, value: 0 }
    run: echo plain
''')


class Args:
    """Mirrors what argparse produces for `run`: a `task` and `task_args`, and
    no `tasks` (its absence is how CmdRun detects single-root mode)."""
    def __init__(self, root, task=None, task_args=None, **kw):
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root
        self.no_summary = True
        if task is not None:
            self.task = task
            self.task_args = task_args or []
            self.task_help = False
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _pkg(proj):
    return loadProjPkgDef(str(proj))


def _params(proj, task_args, defines=None):
    """Run through CmdRun's phase-2 parse and return the resulting node params."""
    loader, pkg = _pkg(proj)
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    from dv_flow.mgr.util import parse_parameter_overrides
    resolver = CLITaskResolver.from_package(pkg)
    overrides = parse_parameter_overrides(defines or [])
    task_ov = overrides['task']
    args = Args(str(proj), task='run-tests', task_args=task_args)
    assert CmdRun()._parse_task_args(args, resolver, task_ov) is None
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                         task_param_overrides=task_ov,
                         leaf_param_overrides=overrides['leaf'])
    return b.mkTaskNode('t.run-tests').params


# ---------------------------------------------------------------------------
# Schema and resolution
# ---------------------------------------------------------------------------

def test_cli_block_parses(proj):
    _, pkg = _pkg(proj)
    cli = resolve_task_cli(pkg.task_m['t.run-tests'])
    assert [a.name for a in cli.args] == ['seed', 'count', 'sim']
    assert cli.args[0].short == 's'
    assert cli.args[2].choices == ['vlt', 'vcs', 'xsim']
    # param defaults to name
    assert cli.args[0].param is None


def test_task_without_cli_resolves_to_none(proj):
    _, pkg = _pkg(proj)
    assert resolve_task_cli(pkg.task_m['t.plain']) is None


def test_cli_is_inherited_and_a_derived_block_replaces_entirely(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: base
        cli:
          args:
          - name: seed
          - name: count
        with:
          seed: { type: int, value: 0 }
          count: { type: int, value: 1 }
      - name: mid
        uses: base
      - name: derived
        uses: base
        cli:
          args:
          - name: seed
    '''))
    monkeypatch.chdir(tmp_path)
    _, pkg = _pkg(tmp_path)
    assert [a.name for a in resolve_task_cli(pkg.task_m['t.mid']).args] == ['seed', 'count']
    # Whole-block replacement, not a per-arg merge: `count` is gone.
    assert [a.name for a in resolve_task_cli(pkg.task_m['t.derived']).args] == ['seed']


def test_cli_arg_may_target_an_inherited_param(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: base
        with:
          seed: { type: int, value: 0 }
      - name: derived
        uses: base
        scope: root
        cli:
          args:
          - name: seed
    '''))
    monkeypatch.chdir(tmp_path)
    _, pkg = _pkg(tmp_path)
    assert resolve_task_cli(pkg.task_m['t.derived']) is not None


# ---------------------------------------------------------------------------
# Load-time validation -- markers, not tracebacks
# ---------------------------------------------------------------------------

def _errors(tmp_path, monkeypatch, flow):
    (tmp_path / 'flow.yaml').write_text(flow)
    monkeypatch.chdir(tmp_path)
    msgs = []
    loadProjPkgDef(str(tmp_path), listener=lambda m: msgs.append(m.msg))
    return msgs


def test_cli_arg_naming_a_missing_param_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: nosuch
    '''))
    assert any("names parameter 'nosuch'" in m for m in msgs)


def test_cli_arg_colliding_with_a_dfm_option_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: clean
        with:
          clean: { type: str, value: "" }
    '''))
    assert any("collides with the dfm option '--clean'" in m for m in msgs)


def test_short_option_colliding_with_a_dfm_option_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: jobs
            short: j
        with:
          jobs: { type: int, value: 1 }
    '''))
    assert any("collides with a dfm option" in m for m in msgs)


def test_duplicate_arg_names_are_markers(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: seed
          - name: seed
        with:
          seed: { type: int, value: 0 }
    '''))
    assert any("declared twice" in m for m in msgs)


def test_multi_character_short_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: seed
            short: sd
        with:
          seed: { type: int, value: 0 }
    '''))
    assert any("single character" in m for m in msgs)


def test_unknown_cli_key_is_rejected_by_the_schema(tmp_path, monkeypatch):
    """`extra='forbid'`, so a typo'd key fails to load rather than being ignored."""
    msgs = _errors(tmp_path, monkeypatch, textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: seed
            shorrt: s
        with:
          seed: { type: int, value: 0 }
    '''))
    assert msgs


# ---------------------------------------------------------------------------
# reserved_options
# ---------------------------------------------------------------------------

def test_reserved_options_span_global_and_subcommand():
    reserved = reserved_options()
    for opt in ("--log-level", "--package-map", "-D", "-P", "--clean", "-j",
                "--report", "--run-id", "--no-summary", "--summary-file", "-u"):
        assert opt in reserved, opt


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def test_parser_uses_readable_metavars_and_help(proj, capsys):
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    parser, dest_param = build_arg_parser(task, resolve_task_cli(task), "dfm run x")
    parser.print_help()
    out = capsys.readouterr().out
    assert "-s SEED, --seed SEED" in out
    # Metavar comes from the arg name, not the mangled dest.
    assert "ARG_SEED" not in out
    # Help and default come from the parameter.
    assert "Base random seed (default: 0)" in out
    assert set(dest_param.values()) == {'seed', 'count', 'sim'}


def test_only_supplied_args_are_returned(proj):
    """An unmentioned flag must leave the param's own default (or a -D) alone."""
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    cli = resolve_task_cli(task)
    assert parse_task_args(task, cli, [], "p") == {}
    assert parse_task_args(task, cli, ["--seed", "42"], "p") == {'seed': 42}


def test_int_type_comes_from_the_param(proj):
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    got = parse_task_args(task, resolve_task_cli(task), ["--count", "7"], "p")
    assert got == {'count': 7} and isinstance(got['count'], int)


def test_bad_choice_exits_with_a_task_scoped_usage(proj, capsys):
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    with pytest.raises(SystemExit):
        parse_task_args(task, resolve_task_cli(task), ["--sim", "nope"],
                        "dfm run t.run-tests")
    err = capsys.readouterr().err
    assert "dfm run t.run-tests" in err
    assert "invalid choice" in err


def test_bool_param_becomes_a_store_true_flag(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        cli:
          args:
          - name: fast
        with:
          fast: { type: bool, value: false }
    '''))
    monkeypatch.chdir(tmp_path)
    _, pkg = _pkg(tmp_path)
    task = pkg.task_m['t.e']
    cli = resolve_task_cli(task)
    assert parse_task_args(task, cli, ["--fast"], "p") == {'fast': True}
    assert parse_task_args(task, cli, [], "p") == {}


def test_list_param_becomes_an_append_flag(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        cli:
          args:
          - name: top
        with:
          top: { type: list, value: [] }
    '''))
    monkeypatch.chdir(tmp_path)
    _, pkg = _pkg(tmp_path)
    task = pkg.task_m['t.e']
    got = parse_task_args(task, resolve_task_cli(task),
                          ["--top", "a", "--top", "b"], "p")
    assert got == {'top': ['a', 'b']}


# ---------------------------------------------------------------------------
# Binding and precedence
# ---------------------------------------------------------------------------

def test_bare_flag_sets_the_param(proj):
    assert _params(proj, ["--seed", "42"]).seed == 42


def test_explicit_separator_is_equivalent(proj):
    """`--` is supported but not required; argparse strips it in phase 1."""
    assert _params(proj, ["--seed", "42"]).seed == 42


def test_short_option_works(proj):
    assert _params(proj, ["-s", "9"]).seed == 9


def test_named_arg_beats_a_define(proj):
    """The ordering trap: kwargs would have lost to -D, so binding goes through
    the override map instead."""
    assert _params(proj, ["--seed", "42"], defines=["seed=7"]).seed == 42
    assert _params(proj, ["--seed", "42"], defines=["t.run-tests.seed=7"]).seed == 42


def test_define_still_applies_when_no_flag_is_given(proj):
    assert _params(proj, [], defines=["seed=7"]).seed == 7


def test_named_arg_scopes_to_the_root_only(proj):
    """A `--seed` sets only the invoked root, while a bare `-D seed=` still
    reaches every task with a `seed` param. The two mechanisms scope
    differently by design."""
    loader, pkg = _pkg(proj)
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    task_ov = {}
    args = Args(str(proj), task='run-tests', task_args=["--seed", "42"])
    CmdRun()._parse_task_args(args, CLITaskResolver.from_package(pkg), task_ov)

    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                         task_param_overrides=task_ov)
    assert b.mkTaskNode('t.run-tests').params.seed == 42
    # `plain` also has a `seed` param, and must NOT pick up the root's flag.
    assert b.mkTaskNode('t.plain').params.seed == 0

    # ...whereas the bare -D form does reach it.
    b2 = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                          leaf_param_overrides={'seed': '7'})
    assert b2.mkTaskNode('t.plain').params.seed == 7


def test_binding_is_keyed_on_the_full_name_not_the_leaf(proj):
    """The override map also matches leaf names, so a leaf-keyed entry would
    leak a root flag into any nested task sharing that leaf name."""
    loader, pkg = _pkg(proj)
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    task_ov = {}
    args = Args(str(proj), task='run-tests', task_args=["--seed", "42"])
    CmdRun()._parse_task_args(args, CLITaskResolver.from_package(pkg), task_ov)
    assert list(task_ov.keys()) == ['t.run-tests']


# ---------------------------------------------------------------------------
# CmdRun-level behavior
# ---------------------------------------------------------------------------

def test_args_to_a_task_with_no_cli_block_are_an_error(proj, capsys):
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    _, pkg = _pkg(proj)
    args = Args(str(proj), task='plain', task_args=["--seed", "1"])
    rc = CmdRun()._parse_task_args(args, CLITaskResolver.from_package(pkg), {})
    assert rc == 1
    err = capsys.readouterr().err
    assert "accepts no arguments" in err
    assert "-D name=value" in err


def test_unknown_task_is_reported(proj, capsys):
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    _, pkg = _pkg(proj)
    args = Args(str(proj), task='nosuch')
    assert CmdRun()._parse_task_args(
        args, CLITaskResolver.from_package(pkg), {}) == 1


def test_task_help_renders_the_usage_view(proj, capsys):
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    _, pkg = _pkg(proj)
    args = Args(str(proj), task='run-tests', task_help=True)
    assert CmdRun()._parse_task_args(
        args, CLITaskResolver.from_package(pkg), {}) == 0
    out = capsys.readouterr().out
    assert "Usage: dfm run t.run-tests" in out
    assert "-s, --seed" in out
    assert "--sim" in out


def test_cli_on_a_nested_task_is_inert_for_run(proj, capsys):
    """`run` never enters phase 2, so a flow with `cli:` blocks runs unchanged."""
    args = Args(str(proj))
    args.tasks = ['run-tests']
    assert CmdRun()(args) == 0


# ---------------------------------------------------------------------------
# show task --usage reflects the cli block
# ---------------------------------------------------------------------------

def test_usage_view_marks_first_class_flags(proj):
    from dv_flow.mgr.cmds.show.usage import build_usage_info
    _, pkg = _pkg(proj)
    info = build_usage_info(pkg.task_m['t.run-tests'])
    seed = next(a for a in info['args'] if a['param'] == 'seed')
    assert seed['name'] == '--seed'
    assert seed['short'] == '-s'
    sim = next(a for a in info['args'] if a['param'] == 'sim')
    assert sim['choices'] == ['vlt', 'vcs', 'xsim']


def test_usage_view_leaves_undeclared_params_as_define_only(proj):
    from dv_flow.mgr.cmds.show.usage import build_usage_info
    _, pkg = _pkg(proj)
    info = build_usage_info(pkg.task_m['t.plain'])
    assert info['args'][0]['name'] is None
    assert info['args'][0]['define'] == '-D plain.seed=VALUE'


# ---------------------------------------------------------------------------
# Two-phase parse at the parser level
# ---------------------------------------------------------------------------

def test_phase1_leaves_task_args_alone():
    args, extra = get_parser().parse_known_args(
        ["run", "run-tests", "-j", "4", "--seed", "42"])
    assert args.task == "run-tests"
    assert args.j == 4
    assert extra == ["--seed", "42"]


def test_phase1_accepts_an_explicit_separator():
    args, extra = get_parser().parse_known_args(
        ["run", "run-tests", "--", "--seed", "42"])
    assert args.task == "run-tests"
    assert extra == ["--seed", "42"]


def test_phase1_extra_positional_becomes_a_task_arg():
    """With bare task args accepted, a second positional is no longer an
    argparse error -- phase 2 rejects it against the task's own parser."""
    args, extra = get_parser().parse_known_args(["run", "run-tests", "other"])
    assert args.task == "run-tests"
    assert extra == ["other"]


def test_task_help_is_deferred_not_intercepted():
    args, _ = get_parser().parse_known_args(["run", "run-tests", "--help"])
    assert args.task_help is True
    assert args.task == "run-tests"


def test_run_with_no_task_still_parses():
    args, _ = get_parser().parse_known_args(["run", "--help"])
    assert args.task is None and args.task_help is True


def test_run_still_rejects_unknown_options():
    with pytest.raises(SystemExit):
        get_parser().parse_args(["run", "build", "--nosuch"])


def test_only_run_is_marked_for_two_phase_parsing():
    """`graph` and `complete --task` also have a `task` attribute, so `run` is
    identified by a marker the run subparser sets, not by attribute sniffing."""
    parser = get_parser()
    assert hasattr(parser.parse_args(["run", "t"]), "run_parser")
    for argv in (["graph", "t"], ["complete", "--task", "t"]):
        assert not hasattr(parser.parse_args(argv), "run_parser"), argv


# ---------------------------------------------------------------------------
# Flag completion
# ---------------------------------------------------------------------------

class CompleteArgs:
    def __init__(self, root, prefix='', task=None):
        self.root = root
        self.prefix = prefix
        self.task = task
        self.config = None
        self.package_map = []


def test_complete_lists_task_flags(proj, capsys):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj), task='run-tests'))
    out = capsys.readouterr().out.split()
    assert out == ['--seed', '-s', '--count', '--sim']


def test_complete_filters_flags_by_prefix(proj, capsys):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj), prefix='--s', task='run-tests'))
    assert capsys.readouterr().out.split() == ['--seed', '--sim']


def test_complete_without_task_still_lists_task_names(proj, capsys):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj)))
    assert 'run-tests' in capsys.readouterr().out


def test_complete_is_quiet_for_a_task_with_no_cli_or_no_such_task(proj, capsys):
    """Completion must never be the thing that fails."""
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj), task='plain'))
    CmdComplete()(CompleteArgs(str(proj), task='nosuch'))
    assert capsys.readouterr().out == ''
