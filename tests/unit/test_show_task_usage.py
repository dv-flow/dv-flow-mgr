"""
`dfm show task <name> --usage` -- the CLI-shaped view of a task.

Also covers the inheritance fix this view depends on: a task's `param_defs`
holds only its own declarations, so anything reading it directly under-reports
a task that gets params via `uses:`.
"""
import json
import textwrap

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.cmds.show.cmd_show_task import CmdShowTask
from dv_flow.mgr.cmds.show.usage import (
    build_usage_info, render_usage_text, _type_name)
from dv_flow.mgr.task import collect_task_params
from dv_flow.mgr.util import loadProjPkgDef


FLOW = textwrap.dedent('''\
package:
  name: p
  tasks:
  - name: base
    with:
      basep:
        type: str
        value: "b"
        doc: "Inherited parameter"
  - name: entry
    uses: base
    scope: root
    desc: "Entry point"
    with:
      seed:
        type: int
        value: 0
        doc: "Base random seed"
      nodoc:
        type: str
        value: ""
    run: echo entry
  - name: noparams
    scope: root
    run: echo noparams
''')


class Args:
    def __init__(self, name, root, **kw):
        self.name = name
        self.root = root
        self.param_overrides = []
        self.config = None
        self.needs = None
        self.json = False
        self.verbose = False
        self.usage = False
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _task(proj, name):
    loader, pkg = loadProjPkgDef(str(proj))
    return pkg.task_m[name]


# ---------------------------------------------------------------------------
# Param inheritance (the fix --usage depends on)
# ---------------------------------------------------------------------------

def test_collect_task_params_includes_inherited(proj):
    task = _task(proj, 'p.entry')
    # Only own declarations are in param_defs...
    assert set(task.param_defs.definitions) == {'seed', 'nodoc'}
    # ...but the task really has the base's param too.
    definitions, types = collect_task_params(task)
    assert set(definitions) == {'seed', 'nodoc', 'basep'}
    assert types['seed'] is int


def test_collect_task_params_nearest_declaration_wins(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: p
      tasks:
      - name: base
        with:
          v:
            type: str
            value: "base"
      - name: derived
        uses: base
        with:
          v:
            type: str
            value: "derived"
    '''))
    monkeypatch.chdir(tmp_path)
    definitions, _ = collect_task_params(_task(tmp_path, 'p.derived'))
    assert definitions['v'].value == "derived"


def test_show_task_lists_inherited_params(proj, capsys):
    CmdShowTask()(Args('entry', str(proj)))
    out = capsys.readouterr().out
    assert 'basep' in out
    assert 'seed' in out


def test_define_reaches_an_inherited_param(proj, capsys, monkeypatch):
    """The user-visible half of the fix: `-D <task>.<inherited>=` used to raise
    'Parameter not found'."""
    from dv_flow.mgr.cmds.cmd_run import CmdRun

    class RunArgs:
        def __init__(self, root, tasks, defines):
            self.tasks = tasks
            self.ui = 'log'
            self.clean = False
            self.j = -1
            self.param_overrides = defines
            self.config = None
            self.root = root

    assert CmdRun()(RunArgs(str(proj), ['entry'], ['p.entry.basep=zz'])) == 0


def test_bare_define_reaches_an_inherited_param(proj):
    """The bare form must agree with the qualified form about what a task has."""
    from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
    loader, pkg = loadProjPkgDef(str(proj))
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                         leaf_param_overrides={'basep': 'zz'})
    assert b.mkTaskNode('p.entry').params.basep == 'zz'


def test_override_of_inherited_param_does_not_leak_to_siblings(proj):
    """An inherited ParamDef is the base's shared object -- writing the coerced
    value back into it would change the default for every derived task."""
    from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
    loader, pkg = loadProjPkgDef(str(proj))
    base_pdef = pkg.task_m['p.base'].param_defs.definitions['basep']
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
                         task_param_overrides={'p.entry': {'basep': 'zz'}})
    assert b.mkTaskNode('p.entry').params.basep == 'zz'
    assert base_pdef.value == 'b'


# ---------------------------------------------------------------------------
# build_usage_info / render_usage_text
# ---------------------------------------------------------------------------

def test_usage_info_lists_every_param_sorted(proj):
    info = build_usage_info(_task(proj, 'p.entry'))
    assert [a['param'] for a in info['args']] == ['basep', 'nodoc', 'seed']
    assert info['task'] == 'p.entry'
    assert info['desc'] == 'Entry point'
    assert info['usage'].startswith('dfm run p.entry')


def test_usage_info_arg_fields(proj):
    info = build_usage_info(_task(proj, 'p.entry'))
    seed = next(a for a in info['args'] if a['param'] == 'seed')
    assert seed['type'] == 'INT'
    assert seed['default'] == 0
    assert seed['help'] == 'Base random seed'
    assert seed['define'] == '-D entry.seed=VALUE'
    # No task can declare first-class flags yet.
    assert seed['name'] is None and seed['short'] is None and seed['choices'] is None


def test_usage_info_for_a_task_with_no_params(proj):
    info = build_usage_info(_task(proj, 'p.noparams'))
    assert info['args'] == []
    assert '(none)' in render_usage_text(info)


def test_render_usage_text_handles_missing_doc(proj):
    """A param with no doc renders with a blank column, not a crash."""
    text = render_usage_text(build_usage_info(_task(proj, 'p.entry')))
    assert 'nodoc' in text
    assert 'Base random seed' in text


def test_render_usage_text_has_no_ansi(proj):
    text = render_usage_text(build_usage_info(_task(proj, 'p.entry')))
    assert '\x1b[' not in text


def test_type_name_maps_python_types():
    assert _type_name(int) == 'INT'
    assert _type_name(str) == 'STR'
    assert _type_name(None) == 'any'


# ---------------------------------------------------------------------------
# CmdShowTask --usage
# ---------------------------------------------------------------------------

def test_usage_flag_renders_the_usage_view(proj, capsys):
    assert CmdShowTask()(Args('entry', str(proj), usage=True)) == 0
    out = capsys.readouterr().out
    assert 'Usage: dfm run p.entry' in out
    assert 'Task arguments:' in out
    assert 'seed' in out
    # Not the detail view.
    assert 'Direct Needs' not in out


def test_usage_output_is_plain_when_not_a_terminal(proj, capsys):
    CmdShowTask()(Args('entry', str(proj), usage=True))
    assert '\x1b[' not in capsys.readouterr().out


def test_usage_and_json_are_orthogonal(proj, capsys):
    """`--json` is a format switch, as it is for every other show subcommand."""
    assert CmdShowTask()(Args('entry', str(proj), usage=True, json=True)) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['task'] == 'p.entry'
    assert {a['param'] for a in doc['args']} == {'basep', 'nodoc', 'seed'}


def test_usage_on_unknown_task_reports_not_found(proj, capsys):
    assert CmdShowTask()(Args('nosuch', str(proj), usage=True)) == 1
    assert 'not found' in capsys.readouterr().out


def test_default_show_task_output_is_unchanged(proj, capsys):
    """`--usage` is opt-in; the detail view must be untouched by its presence."""
    CmdShowTask()(Args('noparams', str(proj)))
    out = capsys.readouterr().out
    assert 'Task: p.noparams' in out
    assert 'Direct Needs' in out
    assert 'Usage:' not in out


def test_parser_accepts_usage_flag():
    args = get_parser().parse_args(["show", "task", "entry", "--usage"])
    assert args.usage is True
    assert get_parser().parse_args(["show", "task", "entry"]).usage is False
