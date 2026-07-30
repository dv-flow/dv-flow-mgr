#****************************************************************************
#* test_cli_needs.py
#*
#* `dfm run <task> --needs <task>`: supplying an input from the command line.
#*
#* A command-line need is the SAME EDGE as one written in `needs:` -- that is
#* the whole point of the spelling. So it resolves through the same name
#* resolver, it is additive rather than replacing, and its data reaches the task
#* the same way. It applies to the invoked task only.
#****************************************************************************
import json
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.cli_task_resolver import CLITaskResolver
from dv_flow.mgr.cmds.cmd_run import CmdRun
from dv_flow.mgr.util import loadProjPkgDef


FLOW = '''\
package:
    name: p
    tasks:
    - {name: art-opt,  uses: std.FileSet, with: {type: art, base: ".", include: ["*.opt"]}}
    - {name: art-prof, uses: std.FileSet, with: {type: art, base: ".", include: ["*.prof"]}}
    - {name: declared, uses: std.FileSet, with: {type: art, base: ".", include: ["*.dec"]}}

    - root: analyze
      uses: std.Message
      needs: [declared]
      with: {msg: analyzing}

    # A compound root: it consumes through `input`, not `needs`.
    - root: analyze-compound
      tasks:
      - {name: inner, uses: std.Message, with: {msg: inner}}

    - name: sim-img
      strategy:
        select:
          axes: {build: [opt, prof]}
        body:
        - uses: std.Message
          with: {msg: "img ${{ this.build }}"}
'''


class Args:
    """What argparse produces for `run`, plus --needs."""
    def __init__(self, root, task, needs=None):
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root
        self.no_summary = True
        self.task = task
        self.task_args = []
        self.task_help = False
        self.needs = needs or []


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'flow.dv').write_text(textwrap.dedent(FLOW))
    for f in ('a.opt', 'b.prof', 'c.dec'):
        (tmp_path / f).write_text('')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _wire(proj, task, needs):
    """Build `task` with `--needs`, returning (node, exit-status-or-None)."""
    loader, pkg = loadProjPkgDef(str(proj))
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(proj / "rundir"), loader=loader)
    resolver = CLITaskResolver.from_package(pkg)
    node = b.mkTaskNode(task)
    rc = CmdRun()._wire_cli_needs(Args(str(proj), task, needs), b, resolver, node)
    return node, rc


def _need_names(node):
    return [n.name for n, _ in node.needs]


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def test_a_cli_need_is_wired(proj):
    node, rc = _wire(proj, "p.analyze", ["art-prof"])
    assert rc is None
    assert "p.art-prof" in _need_names(node)


def test_a_cli_need_is_additive(proj):
    """It adds to what the task declares; it never replaces it. A flag that
    silently dropped a declared dependency would break the build in a way the
    user did not ask for."""
    node, _ = _wire(proj, "p.analyze", ["art-prof"])
    assert "p.declared" in _need_names(node)
    assert "p.art-prof" in _need_names(node)


def test_several_cli_needs_are_all_wired(proj):
    node, _ = _wire(proj, "p.analyze", ["art-opt", "art-prof"])
    for n in ("p.art-opt", "p.art-prof", "p.declared"):
        assert n in _need_names(node)


def test_a_cli_need_resolves_by_partial_name(proj):
    """Same resolver as the task spec, so the shortest unambiguous suffix
    works -- a command-line need should not need more ceremony than the task."""
    node, _ = _wire(proj, "p.analyze", ["art-prof"])
    assert "p.art-prof" in _need_names(node)


def test_a_cli_need_may_be_a_select_cell(proj):
    """The motivating case: hand a specific artifact variant to a task that
    lives in another package and is not in this project's run surface."""
    node, _ = _wire(proj, "p.analyze", ["sim-img.prof"])
    assert "p.sim-img.prof" in _need_names(node)


def test_a_cli_need_on_a_compound_reaches_its_input(proj):
    """A compound consumes through `input`, not `needs` -- the same distinction
    that made deferred cell needs invisible to a compound body. Without it,
    `--needs` on a compound root is accepted and silently does nothing."""
    node, rc = _wire(proj, "p.analyze-compound", ["art-prof"])
    assert rc is None
    assert "p.art-prof" in _need_names(node)
    assert "p.art-prof" in [n.name for n, _ in node.input.needs]


def test_no_cli_needs_changes_nothing(proj):
    node, rc = _wire(proj, "p.analyze", [])
    assert rc is None
    assert _need_names(node) == ["p.declared"]


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

def test_an_unknown_need_is_reported_and_stops_the_run(proj, capsys):
    node, rc = _wire(proj, "p.analyze", ["nosuch"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--needs nosuch" in err
    assert "not found" in err


def test_an_ambiguous_partial_cell_key_is_reported(proj, capsys):
    """A partial key that could bind two axes is an error here too -- the
    resolver is shared, so the diagnostic is the same one `dfm run` gives."""
    (proj / 'flow.dv').write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - root: analyze
          uses: std.Message
          with: {msg: a}
        - name: img
          strategy:
            select:
              axes:
                a: [x, shared]
                b: [y, shared]
            body:
            - uses: std.Message
              with: {msg: hi}
    '''))
    node, rc = _wire(proj, "p.analyze", ["img.shared"])
    assert rc == 1
    assert "ambiguous" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# End to end -- the data actually arrives
# ---------------------------------------------------------------------------

def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


CONSUMER_FLOW = '''\
package:
    name: p
    tasks:
    - {name: art-opt,  uses: std.FileSet, with: {type: art, base: ".", include: ["*.opt"]}}
    - {name: art-prof, uses: std.FileSet, with: {type: art, base: ".", include: ["*.prof"]}}
    - root: analyze
      shell: bash
      consumes: all
      run: |
        cp ${{ rundir }}/dfm.inputs.json ${{ rundir }}/../seen.json
'''


def test_the_supplied_input_reaches_the_task(tmp_path):
    """Not just wired in the graph -- the data item is in what the task
    consumes, which is what a `--needs` is for."""
    (tmp_path / 'flow.dv').write_text(textwrap.dedent(CONSUMER_FLOW))
    (tmp_path / 'a.opt').write_text('')
    (tmp_path / 'b.prof').write_text('')

    proc = _dfm(tmp_path, "analyze", "--needs", "art-prof")
    assert proc.returncode == 0, proc.stderr
    seen = json.loads((tmp_path / "rundir" / "seen.json").read_text())
    blob = json.dumps(seen)
    assert "b.prof" in blob
    assert "a.opt" not in blob


def test_an_unwired_variant_is_not_built(tmp_path):
    """`--needs` selects; it does not pull in siblings."""
    (tmp_path / 'flow.dv').write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - root: analyze
          uses: std.Message
          with: {msg: a}
        - name: img
          strategy:
            select:
              axes: {build: [opt, prof]}
            body:
            - shell: bash
              run: touch ${{ rundir }}/../BUILT-${{ this.build }}
    '''))
    proc = _dfm(tmp_path, "analyze", "--needs", "img.prof")
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(os.path.join(tmp_path, "rundir", "BUILT-prof"))
    assert not os.path.exists(os.path.join(tmp_path, "rundir", "BUILT-opt"))


def test_the_option_is_documented_in_help():
    proc = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run", "--help"],
        capture_output=True, text=True)
    assert "--needs" in proc.stdout
