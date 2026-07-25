"""Parameter value sets: `values:` on a parameter declaration.

Two layers are covered here. The pure-function layer (`ParamDef` parsing and
`param_types.check_value_set`) is exercised directly; the integration layer
checks that the *same* declaration is enforced on every path that can set a
parameter -- the declaration itself, a `uses:`/`with:` override, `-D`, and a
task's own `--flag` -- because a value set attached to only one of them is the
problem this feature exists to fix.
"""
import textwrap

import pytest

from dv_flow.mgr.param_def import ParamDef, ValueSet
from dv_flow.mgr.param_types import (
    ParamValueError, TypeKind, check_value_set, format_value_error,
    value_set_members)
from dv_flow.mgr.task import collect_param_value_sets
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


#---------------------------------------------------------------------------
# Declaration forms
#---------------------------------------------------------------------------

def test_plain_list_is_a_closed_set():
    p = ParamDef(type="str", value="a", values=["a", "b"])
    assert p.values.values() == ["a", "b"]
    assert p.values.open is False
    assert all(e.desc is None for e in p.values.of)


def test_documented_values():
    p = ParamDef(values=[{"value": "quiet", "desc": "headline only"}, "full"])
    assert p.values.values() == ["quiet", "full"]
    assert p.values.of[0].desc == "headline only"
    # A bare value mixed in with documented ones is still a member.
    assert p.values.of[1].desc is None


def test_open_set_form():
    p = ParamDef(values={"of": ["vlt", "vcs"], "open": True})
    assert p.values.open is True
    assert p.values.describe() == "vlt, vcs, ..."


def test_value_set_passes_through():
    vs = ValueSet(of=[{"value": 1}])
    assert ParamDef(values=vs).values is vs


def test_absent_value_set_is_none():
    assert ParamDef(type="str", value="a").values is None
    assert ParamDef(type="str").value_set() is None


@pytest.mark.parametrize("bad", [
    {"open": True},        # a map form without 'of' says nothing about values
    "quiet,normal,full",   # a bare string is not a value set
    42,
])
def test_malformed_value_set_is_rejected(bad):
    with pytest.raises(Exception):
        ParamDef(values=bad)


#---------------------------------------------------------------------------
# check_value_set -- the single enforcement policy
#---------------------------------------------------------------------------

def _vs(*values, open=False):
    return ParamDef(values={"of": list(values), "open": open}).values


def test_member_accepted():
    assert check_value_set("full", _vs("quiet", "full"), TypeKind.STR) is None


def test_non_member_raises_for_a_closed_set():
    with pytest.raises(ParamValueError) as e:
        check_value_set("ful", _vs("quiet", "full"), TypeKind.STR)
    assert "not a valid value" in str(e.value)


def test_open_set_warns_instead_of_raising():
    # An open set enumerates the KNOWN values: a site adding a backend to a
    # library's list must not be blocked by that library's declaration.
    msg = check_value_set("slurm", _vs("local", "lsf", open=True), TypeKind.STR)
    assert msg is not None and "not a known value" in msg


def test_error_names_the_alternatives_and_guesses():
    msg = format_value_error("parameter 'detail'", "ful", _vs("quiet", "normal", "full"))
    assert "quiet, normal, full" in msg
    assert "Did you mean 'full'?" in msg


def test_no_suggestion_when_nothing_is_close():
    assert "Did you mean" not in format_value_error("", "zzzzz", _vs("quiet", "full"))


def test_list_set_constrains_elements():
    vs = _vs("rtl", "tlm")
    assert check_value_set(["rtl", "tlm"], vs, TypeKind.LIST) is None
    with pytest.raises(ParamValueError) as e:
        check_value_set(["rtl", "gate"], vs, TypeKind.LIST)
    # The offending element is named, not the whole list.
    assert "'gate'" in str(e.value)


def test_list_set_splits_a_bare_string():
    # A bare string is an accepted alternate form of a list param, so the set
    # must see the same elements the value will eventually have.
    vs = _vs("rtl", "tlm")
    assert check_value_set("rtl,tlm", vs, TypeKind.LIST) is None
    with pytest.raises(ParamValueError):
        check_value_set("rtl,gate", vs, TypeKind.LIST)


def test_empty_scalar_is_treated_as_unset():
    # "" is how an unset scalar is spelled; a value set must not turn "not
    # chosen" into an error.
    assert check_value_set("", _vs("vlt", "vcs"), TypeKind.STR) is None
    assert check_value_set(None, _vs("vlt"), TypeKind.STR) is None
    assert check_value_set([], _vs("vlt"), TypeKind.LIST) is None


def test_map_typed_param_cannot_declare_a_value_set():
    with pytest.raises(ParamValueError) as e:
        check_value_set({"a": 1}, _vs("a"), TypeKind.MAP)
    assert "map-typed" in str(e.value)


def test_bool_is_not_a_member_of_a_numeric_set():
    # True == 1 in Python; a value set must not let that make a bool a member.
    with pytest.raises(ParamValueError):
        check_value_set(True, _vs(1, 2), TypeKind.ANY)
    assert check_value_set(1, _vs(1, 2), TypeKind.ANY) is None


def test_no_set_declared_accepts_anything():
    assert check_value_set("whatever", None, TypeKind.STR) is None
    assert check_value_set("whatever", _vs(), TypeKind.STR) is None


def test_value_set_members_accepts_a_plain_list():
    assert value_set_members(["a", "b"]) == (["a", "b"], False)
    assert value_set_members(None) == ([], False)


#---------------------------------------------------------------------------
# Enforcement across the set paths
#---------------------------------------------------------------------------

FLOW = textwrap.dedent('''\
package:
  name: p
  tasks:
  - name: base
    scope: root
    cli:
      args:
      - name: mode
      - name: views
    with:
      mode:
        type: str
        value: fast
        doc: How to run
        values:
        - {value: fast, desc: "skip the slow checks"}
        - {value: slow, desc: "everything"}
      views:
        type: list
        value: []
        values: [rtl, tlm]
      backend:
        type: str
        value: local
        values: {of: [local, lsf], open: true}
      free:
        type: str
        value: anything
    run: echo base
  - name: derived
    uses: base
    scope: root
    with:
      mode: slow
  - name: narrowed
    uses: base
    scope: root
    with:
      mode:
        type: str
        value: fast
        values: [fast]
  - name: tests
    uses: std.TestRunner
''')

BAD_INHERITED = '''\
  - name: bad
    uses: base
    scope: root
    with:
      mode: medium
'''


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(proj, task, defines=None):
    from dv_flow.mgr.util import parse_parameter_overrides
    loader, pkg = loadProjPkgDef(str(proj))
    overrides = parse_parameter_overrides(defines or [])
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                         task_param_overrides=overrides['task'],
                         leaf_param_overrides=overrides['leaf'])
    return b.mkTaskNode(task).params


def test_declared_default_is_accepted(proj):
    assert _build(proj, 'p.base').mode == "fast"


def test_define_override_is_rejected(proj):
    with pytest.raises(Exception) as e:
        _build(proj, 'p.base', ['base.mode=medium'])
    assert "not a valid value" in str(e.value)
    assert "fast, slow" in str(e.value)


def test_define_override_in_the_set_is_accepted(proj):
    assert _build(proj, 'p.base', ['base.mode=slow']).mode == "slow"


def test_define_checks_list_elements(proj):
    assert _build(proj, 'p.base', ['base.views=rtl,tlm']).views == ["rtl", "tlm"]
    with pytest.raises(Exception) as e:
        _build(proj, 'p.base', ['base.views=rtl,gate'])
    assert "'gate'" in str(e.value)


def test_open_set_allows_an_unlisted_value(proj, caplog):
    # Accepted -- and said out loud, so a typo is still visible.
    assert _build(proj, 'p.base', ['base.backend=slurm']).backend == "slurm"
    assert any("not a known value" in r.message for r in caplog.records)


def test_param_without_a_set_is_unconstrained(proj):
    assert _build(proj, 'p.base', ['base.free=whatever']).free == "whatever"


def test_value_set_is_inherited_and_the_new_default_is_checked(proj):
    # `derived` re-declares only the value; the set comes from `base`.
    _, pkg = loadProjPkgDef(str(proj))
    assert 'mode' in collect_param_value_sets(pkg.task_m['p.derived'])
    assert _build(proj, 'p.derived').mode == "slow"


def test_a_bad_inherited_default_is_rejected(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(FLOW + BAD_INHERITED)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Exception) as e:
        _build(tmp_path, 'p.bad')
    # The case that goes entirely unchecked when the set lives on a `cli:` block.
    assert "not a valid value" in str(e.value)


def test_a_derived_task_replaces_the_set(proj):
    # Whole-set replacement, like `cli:` blocks: `narrowed` accepts only 'fast'.
    _, pkg = loadProjPkgDef(str(proj))
    assert collect_param_value_sets(pkg.task_m['p.narrowed'])['mode'].values() == ["fast"]
    with pytest.raises(Exception):
        _build(proj, 'p.narrowed', ['narrowed.mode=slow'])
    # ...while the base still accepts both.
    assert _build(proj, 'p.base', ['base.mode=slow']).mode == "slow"


#---------------------------------------------------------------------------
# CLI surfaces
#---------------------------------------------------------------------------

def test_flag_choices_default_from_the_param(proj):
    from dv_flow.mgr.cli_args import resolve_task_cli, build_arg_parser
    _, pkg = loadProjPkgDef(str(proj))
    task = pkg.task_m['p.base']
    parser, _ = build_arg_parser(task, resolve_task_cli(task), "dfm run p.base")
    with pytest.raises(SystemExit):
        parser.parse_args(["--mode", "medium"])
    assert parser.parse_args(["--mode", "slow"])


def test_a_list_flag_gets_no_argparse_choices(proj):
    # `--views rtl,tlm` is comma-split AFTER argparse collects it, so installing
    # choices here would reject the joined form. The value-set check still runs
    # when the flag binds through the override map.
    from dv_flow.mgr.cli_args import resolve_task_cli, parse_task_args
    _, pkg = loadProjPkgDef(str(proj))
    task = pkg.task_m['p.base']
    values = parse_task_args(task, resolve_task_cli(task), ["--views", "rtl,tlm"],
                             "dfm run p.base")
    assert values["views"] == ["rtl", "tlm"]


def test_usage_reports_the_set_and_its_documentation(proj):
    from dv_flow.mgr.cmds.show.usage import build_usage_info, render_usage_text
    _, pkg = loadProjPkgDef(str(proj))
    info = build_usage_info(pkg.task_m['p.base'])
    by_param = {a['param']: a for a in info['args']}

    assert by_param['mode']['choices'] == ["fast", "slow"]
    assert by_param['mode']['choices_open'] is False
    assert by_param['mode']['choices_doc'][0]['desc'] == "skip the slow checks"
    # A set on a param with no flag of its own still shows up: `-D` can set it.
    assert by_param['backend']['choices'] == ["local", "lsf"]
    assert by_param['backend']['choices_open'] is True
    assert by_param['free']['choices'] is None

    text = render_usage_text(info)
    assert "(fast, slow)" in text
    assert "skip the slow checks" in text
    # An open set is never presented as exhaustive.
    assert "(local, lsf, ...)" in text


def test_a_cli_choices_narrowing_still_wins(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: t
        scope: root
        cli:
          args:
          - name: mode
            choices: [fast]
        with:
          mode: { type: str, value: fast, values: [fast, slow] }
        run: echo t
    '''))
    monkeypatch.chdir(tmp_path)
    from dv_flow.mgr.cmds.show.usage import build_usage_info
    _, pkg = loadProjPkgDef(str(tmp_path))
    info = build_usage_info(pkg.task_m['p.t'])
    assert [a for a in info['args'] if a['param'] == 'mode'][0]['choices'] == ["fast"]


def test_value_completion(proj):
    from dv_flow.mgr.cmds.cmd_complete import CmdComplete
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    _, pkg = loadProjPkgDef(str(proj))
    resolver = CLITaskResolver.from_package(pkg)
    cmd = CmdComplete()
    assert cmd._value_completions(resolver, 'base', '--mode', '') == ["fast", "slow"]
    assert cmd._value_completions(resolver, 'base', 'mode', 'f') == ["fast"]
    # A param with no set completes nothing rather than guessing.
    assert cmd._value_completions(resolver, 'base', '--free', '') == []


def test_std_testrunner_declares_its_detail_levels(proj):
    # The declaration that motivated the feature: `detail`'s levels were stated
    # in a `cli:` block, in prose, and in test_summary.py, and enforced only on
    # the flag. A task inheriting TestRunner now inherits the set itself.
    _, pkg = loadProjPkgDef(str(proj))
    assert collect_param_value_sets(pkg.task_m['p.tests'])['detail'].values() == \
        ["quiet", "normal", "full"]


def test_bad_detail_is_rejected_wherever_it_is_set(proj):
    with pytest.raises(Exception) as e:
        _build(proj, 'p.tests', ['tests.detail=ful'])
    assert "Did you mean 'full'?" in str(e.value)
