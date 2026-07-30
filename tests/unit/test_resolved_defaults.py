#****************************************************************************
#* test_resolved_defaults.py
#*
#* The CLI-facing views show a parameter's VALUE, not the expression that
#* computes it.
#*
#* A lazily-evaluated default is stored as its source text, so `dfm run <task>
#* --help` and `dfm show task` used to print `[default: ${{ build }}]` where the
#* user wants `[default: opt]`. Both now resolve, and both reflect `-D`, so what
#* is shown is what the invocation would actually use.
#*
#* Resolution is display-only and must never be load-bearing: it builds no
#* nodes, and any failure degrades to showing the declared text rather than
#* breaking the command.
#****************************************************************************
import json
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


FLOW = '''\
package:
    name: p
    with:
      build: {type: str, value: opt}
      root_seed: {type: int, value: 7}
    tasks:
    - root: img
      with:
        build: {type: str, value: "${{ build }}", cli: true, values: [opt, dbg, cov]}
        seed:  {type: int, value: "${{ root_seed }}", cli: true}
        plain: {type: str, value: literal, cli: true}
      strategy:
        select:
          axes:
            build: [opt, dbg, cov]
          default: {build: "${{ build }}"}
        body:
        - uses: std.Message
          with: {msg: "built ${{ this.build }}"}
'''


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(FLOW))
    return tmp_path


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(d), capture_output=True, text=True)


def _builder(proj, overrides=None):
    ov = overrides or {'package': {}, 'task': {}, 'leaf': {}}
    loader, pkg = loadProjPkgDef(str(proj), parameter_overrides=ov)
    return TaskGraphBuilder(
        root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader,
        task_param_overrides=ov.get('task', {}),
        leaf_param_overrides=ov.get('leaf', {})), pkg


# ---------------------------------------------------------------------------
# The builder entry point
# ---------------------------------------------------------------------------

def test_resolve_task_params_evaluates_expressions(proj):
    b, pkg = _builder(proj)
    values = b.resolveTaskParams(pkg.task_m["p.img"])
    assert values["build"] == "opt"
    assert values["seed"] == 7
    assert values["plain"] == "literal"


def test_resolve_task_params_reflects_a_define(proj):
    b, pkg = _builder(proj, {'package': {'build': 'cov'}, 'task': {}, 'leaf': {}})
    assert b.resolveTaskParams(pkg.task_m["p.img"])["build"] == "cov"


def test_resolve_task_params_builds_no_nodes(proj):
    """Describing a task must not build it, or its dependencies -- otherwise a
    display command does work, and can fail for reasons that have nothing to do
    with what was asked."""
    b, pkg = _builder(proj)
    b.resolveTaskParams(pkg.task_m["p.img"])
    assert not b._task_node_m


def test_resolve_select_default(proj):
    b, pkg = _builder(proj)
    assert b.resolveSelectDefault(pkg.task_m["p.img"]) == {"build": "opt"}


def test_resolve_select_default_reflects_a_define(proj):
    b, pkg = _builder(proj, {'package': {'build': 'dbg'}, 'task': {}, 'leaf': {}})
    assert b.resolveSelectDefault(pkg.task_m["p.img"]) == {"build": "dbg"}


def test_resolve_select_default_is_none_for_an_ordinary_task(proj):
    b, pkg = _builder(proj)
    assert b.resolveSelectDefault(pkg.task_m["p.img.opt"]) is None


def test_a_cells_params_resolve_against_its_bindings(proj):
    """A cell's parameters are written against its axis values, so without them
    the cell reports the template rather than what it will run with."""
    b, pkg = _builder(proj)
    values = b.resolveTaskParams(pkg.task_m["p.img.cov"])
    assert values["msg"] == "built cov"


# ---------------------------------------------------------------------------
# dfm run <task> --help
# ---------------------------------------------------------------------------

def test_run_help_shows_resolved_defaults(proj):
    proc = _dfm(proj, "run", "img", "--help")
    assert proc.returncode == 0, proc.stderr
    assert "[default: opt]" in proc.stdout
    assert "${{ build }}" not in proc.stdout
    assert "[default: 7]" in proc.stdout


def test_run_help_reflects_a_define(proj):
    proc = _dfm(proj, "run", "img", "--help", "-D", "build=cov")
    assert proc.returncode == 0, proc.stderr
    assert "[default: cov]" in proc.stdout
    # ...in the argparse block too, not only the usage view.
    assert "(default: cov)" in proc.stdout


# ---------------------------------------------------------------------------
# dfm show task
# ---------------------------------------------------------------------------

def test_show_task_shows_resolved_parameter_values(proj):
    proc = _dfm(proj, "show", "task", "p.img")
    assert proc.returncode == 0, proc.stderr
    assert "= opt" in proc.stdout
    assert "${{ build }}" not in proc.stdout


def test_show_task_shows_the_resolved_select_default(proj):
    proc = _dfm(proj, "show", "task", "p.img")
    assert "default: build=opt" in proc.stdout


def test_show_task_select_default_reflects_a_define(proj):
    proc = _dfm(proj, "show", "task", "p.img", "-D", "build=dbg")
    assert "default: build=dbg" in proc.stdout


def test_show_task_on_a_cell_resolves_its_bindings(proj):
    proc = _dfm(proj, "show", "task", "p.img.cov")
    assert proc.returncode == 0, proc.stderr
    assert "built cov" in proc.stdout
    assert "${{ this.build }}" not in proc.stdout


def test_show_task_usage_shows_resolved_defaults(proj):
    proc = _dfm(proj, "show", "task", "p.img", "--usage")
    assert proc.returncode == 0, proc.stderr
    assert "[default: opt]" in proc.stdout


def test_usage_json_carries_resolved_defaults(proj):
    """The `--usage --json` document is what a completion script or editor
    integration consumes, so it must carry the value, not the expression."""
    proc = _dfm(proj, "show", "task", "p.img", "--usage", "--json")
    info = json.loads(proc.stdout)
    build = next(a for a in info['args'] if a['param'] == 'build')
    assert build['default'] == "opt"


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------

def test_a_task_whose_default_cannot_resolve_still_describes(tmp_path):
    """Resolution is a convenience. A task that cannot be resolved must still
    be describable -- showing the declared text is a worse answer than the
    value, and a much better one than an error."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - root: t
          with:
            a: {type: str, value: "${{ nosuch_var }}"}
          run: echo hi
    '''))
    proc = _dfm(tmp_path, "show", "task", "p.t")
    assert proc.returncode == 0, proc.stderr
    assert "Task: p.t" in proc.stdout


def test_usage_info_still_builds_without_a_project(proj):
    """`build_usage_info` takes resolved values as an OPTION, so the document
    can still be produced when no project context is available."""
    from dv_flow.mgr.cmds.show.usage import build_usage_info
    _, pkg = _builder(proj)
    info = build_usage_info(pkg.task_m["p.img"])
    build = next(a for a in info['args'] if a['param'] == 'build')
    # Unresolved: the declared text, exactly as before this feature.
    assert build['default'] == "${{ build }}"
