"""
Task command-line arguments: `cli:` on a parameter declaration, its load-time
validation, the two-phase `run` parse, and how parsed values bind to params.

The contract being pinned: a parameter that should be settable from the command
line says so *in its own declaration*. There is no separate block to keep in
sync, so type, default, help and accepted values can only come from one place.
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
    with:
      seed:  { type: int, value: 0,   cli: {short: s}, doc: Base random seed }
      count: { type: int, value: 10,  cli: true, doc: Number of iterations }
      sim:   { type: str, value: vlt, cli: true, doc: Simulator backend,
               values: [vlt, vcs, xsim] }
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


def _flow(tmp_path, monkeypatch, text):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent(text))
    monkeypatch.chdir(tmp_path)
    return _pkg(tmp_path)


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
# Declaration and resolution
# ---------------------------------------------------------------------------

def test_declared_flags_are_collected(proj):
    _, pkg = _pkg(proj)
    args = resolve_task_cli(pkg.task_m['t.run-tests'])
    # Declaration order, not alphabetical.
    assert [a.name for a in args] == ['seed', 'count', 'sim']
    assert [a.param for a in args] == ['seed', 'count', 'sim']
    assert args[0].short == 's'
    # `cli: true` is the whole declaration for the common case.
    assert args[1].short is None and args[1].hidden is False


def test_task_exposing_nothing_resolves_to_empty(proj):
    _, pkg = _pkg(proj)
    assert resolve_task_cli(pkg.task_m['t.plain']) == []


def test_help_type_and_default_come_from_the_parameter(proj):
    _, pkg = _pkg(proj)
    seed = resolve_task_cli(pkg.task_m['t.run-tests'])[0]
    assert seed.help == 'Base random seed'
    assert seed.default == 0


def test_flag_may_be_renamed(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          build_variant: { type: str, value: opt, cli: {name: build} }
    ''')
    arg = resolve_task_cli(pkg.task_m['t.e'])[0]
    assert arg.name == 'build' and arg.param == 'build_variant'


def test_flag_name_is_the_param_name_verbatim(tmp_path, monkeypatch):
    """No underscore-to-dash rewriting: the flag and the `-D` form of the same
    parameter must not disagree."""
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          test_key: { type: str, value: name, cli: true }
    ''')
    assert resolve_task_cli(pkg.task_m['t.e'])[0].name == 'test_key'


def test_hidden_flag_parses_but_is_absent_from_help(tmp_path, monkeypatch, capsys):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        with:
          secret: { type: str, value: "", cli: {hidden: true}, doc: Internal }
    ''')
    task = pkg.task_m['t.e']
    args = resolve_task_cli(task)
    assert args[0].hidden is True
    assert parse_task_args(task, args, ["--secret", "x"], "p") == {'secret': 'x'}
    parser, _ = build_arg_parser(task, args, "dfm run t.e")
    parser.print_help()
    assert "--secret" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Inheritance -- per parameter, not per block
# ---------------------------------------------------------------------------

def test_flags_inherit_along_uses(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: base
        with:
          seed:  { type: int, value: 0, cli: true }
          count: { type: int, value: 1, cli: true }
      - name: mid
        uses: base
      - name: derived
        uses: base
        with:
          seed: { type: int, value: 5 }
    ''')
    assert [a.name for a in resolve_task_cli(pkg.task_m['t.mid'])] == ['seed', 'count']
    # Re-declaring a param to change its default says nothing about `cli:`, so
    # the inherited flag survives -- the same rule `values:` follows.
    derived = resolve_task_cli(pkg.task_m['t.derived'])
    assert [a.name for a in derived] == ['seed', 'count']
    assert derived[0].default == 5


def test_cli_false_removes_an_inherited_flag(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: base
        with:
          seed:  { type: int, value: 0, cli: true }
          count: { type: int, value: 1, cli: true }
      - name: derived
        uses: base
        with:
          count: { type: int, value: 1, cli: false }
    ''')
    assert [a.name for a in resolve_task_cli(pkg.task_m['t.derived'])] == ['seed']


def test_a_derived_task_may_add_a_flag(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: base
        with:
          seed: { type: int, value: 0, cli: true }
      - name: derived
        uses: base
        with:
          extra: { type: str, value: "", cli: true }
    ''')
    assert {a.name for a in resolve_task_cli(pkg.task_m['t.derived'])} == {'seed', 'extra'}


# ---------------------------------------------------------------------------
# Load-time validation -- markers, not tracebacks
# ---------------------------------------------------------------------------

def _errors(tmp_path, monkeypatch, flow):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent(flow))
    monkeypatch.chdir(tmp_path)
    msgs = []
    loadProjPkgDef(str(tmp_path), listener=lambda m: msgs.append(m.msg))
    return msgs


def test_flag_colliding_with_a_dfm_option_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          clean: { type: str, value: "", cli: true }
    ''')
    assert any("collides with the dfm option" in m for m in msgs)


def test_short_option_colliding_with_a_dfm_option_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          jobs: { type: int, value: 1, cli: {short: j} }
    ''')
    assert any("collides with a dfm option" in m for m in msgs)


def test_two_params_claiming_one_flag_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          seed:  { type: int, value: 0, cli: true }
          other: { type: int, value: 0, cli: {name: seed} }
    ''')
    assert any("exposes '--seed' twice" in m for m in msgs)


def test_inherited_collision_is_reported_on_the_task_that_has_it(tmp_path, monkeypatch):
    """A collision can be created by inheritance alone, so validation looks at
    the effective flag set rather than only the task's own declarations."""
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: base
        with:
          seed: { type: int, value: 0, cli: true }
      - name: derived
        uses: base
        with:
          other: { type: int, value: 0, cli: {name: seed} }
    ''')
    assert any("exposes '--seed' twice" in m for m in msgs)


def test_multi_character_short_is_a_marker(tmp_path, monkeypatch):
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          seed: { type: int, value: 0, cli: {short: sd} }
    ''')
    assert any("single character" in m for m in msgs)


def test_unknown_cli_key_is_rejected_by_the_schema(tmp_path, monkeypatch):
    """`extra='forbid'` on CliOpt, so a typo fails to load rather than being
    silently ignored -- which would leave the flag quietly unexposed."""
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          seed: { type: int, value: 0, cli: {shorrt: s} }
    ''')
    assert msgs


def test_the_cli_block_is_gone(tmp_path, monkeypatch):
    """`TaskDef` is `extra='forbid'`, so the retired block is a load error and
    not a silently ignored key."""
    msgs = _errors(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        cli:
          args:
          - name: seed
        with:
          seed: { type: int, value: 0 }
    ''')
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
    args = resolve_task_cli(task)
    assert parse_task_args(task, args, [], "p") == {}
    assert parse_task_args(task, args, ["--seed", "42"], "p") == {'seed': 42}


def test_int_type_comes_from_the_param(proj):
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    got = parse_task_args(task, resolve_task_cli(task), ["--count", "7"], "p")
    assert got == {'count': 7} and isinstance(got['count'], int)


def test_choices_come_from_the_declared_value_set(proj, capsys):
    _, pkg = _pkg(proj)
    task = pkg.task_m['t.run-tests']
    with pytest.raises(SystemExit):
        parse_task_args(task, resolve_task_cli(task), ["--sim", "nope"],
                        "dfm run t.run-tests")
    err = capsys.readouterr().err
    assert "dfm run t.run-tests" in err
    assert "invalid choice" in err


def test_an_open_value_set_does_not_restrict_the_flag(tmp_path, monkeypatch):
    """An open set enumerates the *known* values. Blocking an unlisted one at
    the parser would defeat the point -- the value-set check downstream warns."""
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        with:
          sim:
            type: str
            value: vlt
            cli: true
            values: {of: [vlt, vcs], open: true}
    ''')
    task = pkg.task_m['t.e']
    got = parse_task_args(task, resolve_task_cli(task), ["--sim", "questa"], "p")
    assert got == {'sim': 'questa'}


def test_bool_param_becomes_a_store_true_flag(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        with:
          fast: { type: bool, value: false, cli: true }
    ''')
    task = pkg.task_m['t.e']
    args = resolve_task_cli(task)
    assert parse_task_args(task, args, ["--fast"], "p") == {'fast': True}
    assert parse_task_args(task, args, [], "p") == {}


def test_list_param_becomes_an_append_flag(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        with:
          top: { type: list, value: [], cli: true }
    ''')
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


def test_a_renamed_flag_binds_the_parameter_not_the_flag_name(tmp_path, monkeypatch):
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        scope: root
        with:
          build_variant: { type: str, value: opt, cli: {name: build} }
        run: echo hi
    ''')
    task = pkg.task_m['t.e']
    got = parse_task_args(task, resolve_task_cli(task), ["--build", "prof"], "p")
    assert got == {'build_variant': 'prof'}


# ---------------------------------------------------------------------------
# CmdRun-level behavior
# ---------------------------------------------------------------------------

def test_args_to_a_task_exposing_nothing_are_an_error(proj, capsys):
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    _, pkg = _pkg(proj)
    args = Args(str(proj), task='plain', task_args=["--seed", "1"])
    rc = CmdRun()._parse_task_args(args, CLITaskResolver.from_package(pkg), {})
    assert rc == 1
    err = capsys.readouterr().err
    assert "accepts no arguments" in err
    assert "-D name=value" in err
    # The message must say how to fix it in the new spelling.
    assert "cli: true" in err


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


def test_exposed_params_on_a_nested_task_are_inert_for_run(proj, capsys):
    """`run` never enters phase 2 for a nested task, so a flow whose tasks
    expose flags runs unchanged."""
    args = Args(str(proj))
    args.tasks = ['run-tests']
    assert CmdRun()(args) == 0


# ---------------------------------------------------------------------------
# show task --usage reflects the declarations
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


def test_usage_view_omits_a_hidden_flag(tmp_path, monkeypatch):
    from dv_flow.mgr.cmds.show.usage import build_usage_info
    _, pkg = _flow(tmp_path, monkeypatch, '''\
    package:
      name: t
      tasks:
      - name: e
        with:
          secret: { type: str, value: "", cli: {hidden: true} }
    ''')
    info = build_usage_info(pkg.task_m['t.e'])
    secret = next(a for a in info['args'] if a['param'] == 'secret')
    assert secret['name'] is None


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
    def __init__(self, root, prefix='', task=None, flag=None):
        self.root = root
        self.prefix = prefix
        self.task = task
        self.flag = flag
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


def test_complete_offers_values_from_the_declared_set(proj, capsys):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj), task='run-tests', flag='--sim'))
    assert capsys.readouterr().out.split() == ['vlt', 'vcs', 'xsim']


def test_complete_without_task_still_lists_task_names(proj, capsys):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj)))
    assert 'run-tests' in capsys.readouterr().out


def test_complete_is_quiet_for_a_task_with_no_flags_or_no_such_task(proj, capsys):
    """Completion must never be the thing that fails."""
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    CmdComplete()(CompleteArgs(str(proj), task='plain'))
    CmdComplete()(CompleteArgs(str(proj), task='nosuch'))
    assert capsys.readouterr().out == ''
