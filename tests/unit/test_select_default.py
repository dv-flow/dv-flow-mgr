#****************************************************************************
#* test_select_default.py
#*
#* What the bare name of a `select:` family denotes, and the control chain that
#* decides it: package variable -> task parameter -> -D -> --flag -> cell name.
#*
#* The contract being pinned:
#*   * a family is never a unit of work. It is an ALIAS for one cell, a GATE
#*     over several, or (default: none) not addressable at all -- declared, not
#*     guessed;
#*   * the alias and the cell name reach the SAME node, so a project that uses
#*     both spellings builds the artifact once;
#*   * `default:` is an expression over the family's own parameters, which is
#*     what makes one package-level knob move every family in the project.
#****************************************************************************
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
    tasks:
    - root: img
      with:
        view:  {type: str, value: tlm, cli: true, values: [tlm, rtl]}
        build: {type: str, value: "${{ build }}", cli: true,
                values: [opt, prof, cov]}
      strategy:
        select:
          axes:
            view:  [tlm, rtl]
            build: [opt, prof, cov]
          default: {view: "${{ view }}", build: "${{ build }}"}
        body:
        - uses: std.Message
          with: {msg: "view=${{ this.view }} build=${{ this.build }}"}
'''


def _write(tmpdir, flow=FLOW):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(textwrap.dedent(flow))
    return str(tmpdir)


def _node(tmpdir, task="p.img", flow=FLOW, defines=None, flags=None):
    """Build `task` the way `dfm run` would, including the -D/--flag ladder."""
    from dv_flow.mgr.cli_task_resolver import CLITaskResolver
    from dv_flow.mgr.util import parse_parameter_overrides
    from dv_flow.mgr.cmds.cmd_run import CmdRun

    d = _write(tmpdir, flow)
    overrides = parse_parameter_overrides(defines or [])
    loader, pkg = loadProjPkgDef(
        d, parameter_overrides=overrides)
    task_ov = overrides['task']

    if flags:
        class Args:
            pass
        args = Args()
        args.task = task.split('.', 1)[-1] if task.startswith("p.") else task
        args.task_args = flags
        args.task_help = False
        rc = CmdRun()._parse_task_args(
            args, CLITaskResolver.from_package(pkg), task_ov)
        assert rc is None, "phase-2 parse rejected %s" % flags

    b = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"), loader=loader,
        task_param_overrides=task_ov, leaf_param_overrides=overrides['leaf'])
    return b, b.mkTaskNode(task)


# ---------------------------------------------------------------------------
# The control chain
# ---------------------------------------------------------------------------

def test_bare_family_builds_the_default_cell(tmpdir):
    _, node = _node(tmpdir)
    assert node.name == "p.img.tlm.opt"


def test_a_define_on_the_package_variable_moves_the_default(tmpdir):
    """The project-wide knob: one `-D` moves every family that defaults from
    it, without touching the flow file."""
    _, node = _node(tmpdir, defines=["build=cov"])
    assert node.name == "p.img.tlm.cov"


def test_a_flag_moves_the_default(tmpdir):
    _, node = _node(tmpdir, flags=["--build", "prof"])
    assert node.name == "p.img.tlm.prof"


def test_a_flag_beats_a_define(tmpdir):
    _, node = _node(tmpdir, defines=["build=cov"], flags=["--build", "prof"])
    assert node.name == "p.img.tlm.prof"


def test_flags_on_several_axes(tmpdir):
    _, node = _node(tmpdir, flags=["--view", "rtl", "--build", "cov"])
    assert node.name == "p.img.rtl.cov"


def test_omitted_default_is_the_first_value_of_each_axis(tmpdir):
    _, node = _node(tmpdir, task="p.img", flow='''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                view: [tlm, rtl]
                build: [opt, prof]
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    assert node.name == "p.img.tlm.opt"


def test_a_partial_default_defaults_the_rest(tmpdir):
    _, node = _node(tmpdir, flow='''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                view: [tlm, rtl]
                build: [opt, prof]
              default: {build: prof}
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    assert node.name == "p.img.tlm.prof"


# ---------------------------------------------------------------------------
# Alias identity
# ---------------------------------------------------------------------------

def test_the_alias_and_the_cell_name_reach_one_node(tmpdir):
    """Otherwise a project that says `needs: [img]` in one place and
    `needs: [img.tlm.opt]` in another builds the artifact twice."""
    b, node = _node(tmpdir)
    assert b.mkTaskNode("p.img.tlm.opt") is node
    assert b._task_node_m["p.img"] is node


def test_the_alias_builds_only_the_default_cell(tmpdir):
    b, _ = _node(tmpdir)
    assert sorted(k for k in b._task_node_m if k.startswith("p.img.")) == \
        ["p.img.tlm.opt"]


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

ALL_FLOW = '''\
package:
    name: p
    tasks:
    - root: img
      strategy:
        select:
          axes:
            build: [opt, prof, cov]
          default: all
        body:
        - uses: std.Message
          with: {msg: "${{ this.build }}"}
'''


def test_default_all_gates_every_cell(tmpdir):
    b, node = _node(tmpdir, flow=ALL_FLOW)
    assert node.name == "p.img"
    assert sorted(k for k in b._task_node_m if k.startswith("p.img.")) == \
        ["p.img.cov", "p.img.opt", "p.img.prof"]


def test_a_multi_valued_default_gates_a_sub_family(tmpdir):
    b, node = _node(tmpdir, flow='''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                build: [opt, prof, cov]
              default: {build: [opt, cov]}
            body:
            - uses: std.Message
              with: {msg: "${{ this.build }}"}
    ''')
    assert sorted(k for k in b._task_node_m if k.startswith("p.img.")) == \
        ["p.img.cov", "p.img.opt"]


def test_a_comma_list_flag_gates_a_sub_family(tmpdir):
    b, node = _node(tmpdir, flow='''\
    package:
        name: p
        tasks:
        - root: img
          with:
            build: {type: list, value: [opt], cli: true}
          strategy:
            select:
              axes:
                build: [opt, prof, cov]
              default: {build: "${{ build }}"}
            body:
            - uses: std.Message
              with: {msg: "${{ this.build }}"}
    ''', flags=["--build", "prof,cov"])
    assert sorted(k for k in b._task_node_m if k.startswith("p.img.")) == \
        ["p.img.cov", "p.img.prof"]


def test_default_none_makes_the_family_unaddressable(tmpdir):
    """A catalog with no meaningful "the" artifact says so, rather than
    silently building nothing."""
    with pytest.raises(Exception) as e:
        _node(tmpdir, flow='''\
        package:
            name: p
            tasks:
            - root: img
              strategy:
                select:
                  axes:
                    build: [opt, prof]
                  default: none
                body:
                - uses: std.Message
                  with: {msg: hi}
        ''')
    assert "cannot be built or depended on directly" in str(e.value)
    # ...and it names the cells, so the error is actionable.
    assert "p.img.opt" in str(e.value)


def test_a_cell_of_a_none_family_still_builds(tmpdir):
    _, node = _node(tmpdir, task="p.img.prof", flow='''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                build: [opt, prof]
              default: none
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    assert node.name == "p.img.prof"


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

def test_a_default_outside_the_axis_is_rejected(tmpdir):
    """A family whose parameter declares `values:` is caught by the parameter
    check -- the same message `-D` and `--flag` already produce."""
    with pytest.raises(Exception) as e:
        _node(tmpdir, defines=["build=nosuch"])
    assert "not a valid value" in str(e.value)
    assert "opt, prof, cov" in str(e.value)


def test_an_undeclared_value_set_still_fails_at_the_axis(tmpdir):
    """The backstop, for a family that did not declare `values:` on its
    parameter: the axis itself is the authority, and the error names it rather
    than surfacing later as a missing task."""
    with pytest.raises(Exception) as e:
        _node(tmpdir, defines=["build=nosuch"], flow='''\
        package:
            name: p
            tasks:
            - root: img
              with:
                build: {type: str, value: opt}
              strategy:
                select:
                  axes:
                    build: [opt, prof, cov]
                  default: {build: "${{ build }}"}
                body:
                - uses: std.Message
                  with: {msg: hi}
        ''')
    assert "not a value of select axis 'build'" in str(e.value)
    assert "opt, prof, cov" in str(e.value)


def test_a_flag_outside_the_declared_value_set_is_rejected_earlier(tmpdir):
    """The parameter's own `values:` catches it at the parser, before the graph
    is touched at all."""
    with pytest.raises(SystemExit):
        _node(tmpdir, flags=["--build", "nosuch"])


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


def test_cli_selection_end_to_end(tmpdir):
    d = _write(tmpdir)
    proc = _dfm(d, "img", "--build", "prof")
    assert proc.returncode == 0, proc.stderr
    assert "view=tlm build=prof" in proc.stdout
    assert os.path.isdir(os.path.join(d, "rundir", "p.img.tlm.prof"))
    # No sibling was built.
    assert not os.path.exists(os.path.join(d, "rundir", "p.img.tlm.opt"))


def test_cell_addressed_by_name_end_to_end(tmpdir):
    d = _write(tmpdir)
    proc = _dfm(d, "img.rtl.cov")
    assert proc.returncode == 0, proc.stderr
    assert "view=rtl build=cov" in proc.stdout


# ---------------------------------------------------------------------------
# Partial cell keys -- command line only (design decision 7)
# ---------------------------------------------------------------------------

def test_a_partial_key_binds_the_axis_it_names(tmpdir):
    d = _write(tmpdir)
    proc = _dfm(d, "img.prof")
    assert proc.returncode == 0, proc.stderr
    assert "view=tlm build=prof" in proc.stdout


def test_a_partial_key_takes_the_rest_from_the_default(tmpdir):
    """...including a default a -D has moved, which is exactly why this is a
    command-line convenience and not something a flow file may say."""
    d = _write(tmpdir)
    proc = _dfm(d, "-D", "view=rtl", "img.prof")
    assert proc.returncode == 0, proc.stderr
    assert "view=rtl build=prof" in proc.stdout


def test_a_partial_key_may_name_any_axis(tmpdir):
    d = _write(tmpdir)
    proc = _dfm(d, "img.rtl")
    assert proc.returncode == 0, proc.stderr
    assert "view=rtl build=opt" in proc.stdout


def test_two_values_for_one_axis_is_ambiguous(tmpdir):
    d = _write(tmpdir)
    proc = _dfm(d, "img.opt.prof")
    assert proc.returncode != 0
    assert "ambiguous" in proc.stderr


def test_a_value_shared_by_two_axes_is_ambiguous(tmpdir):
    d = _write(tmpdir, '''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                a: [x, shared]
                b: [y, shared]
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    proc = _dfm(d, "img.shared")
    assert proc.returncode != 0
    assert "ambiguous" in proc.stderr
    assert "more than one axis" in proc.stderr


def test_a_partial_key_in_needs_is_a_load_error(tmpdir):
    """A build file must not change meaning because a default moved. The error
    names the full keys it could have meant."""
    from dv_flow.mgr.util import loadProjPkgDef
    d = _write(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                view: [tlm, rtl]
                build: [opt, prof]
            body:
            - uses: std.Message
              with: {msg: hi}
        - root: consumer
          uses: std.Message
          needs: [img.prof]
          with: {msg: c}
    ''')
    msgs = []
    loadProjPkgDef(d, listener=lambda m: msgs.append(m.msg))
    assert any("by a partial key" in m for m in msgs)
    assert any("p.img.tlm.prof" in m for m in msgs)


def test_a_full_key_in_needs_is_fine(tmpdir):
    from dv_flow.mgr.util import loadProjPkgDef
    d = _write(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                view: [tlm, rtl]
                build: [opt, prof]
            body:
            - uses: std.Message
              with: {msg: hi}
        - root: consumer
          uses: std.Message
          needs: [img.tlm.prof]
          with: {msg: c}
    ''')
    msgs = []
    loadProjPkgDef(d, listener=lambda m: msgs.append(m.msg))
    assert not msgs, msgs
