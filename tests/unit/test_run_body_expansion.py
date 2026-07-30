"""Phase B/C of run_body_expansion_plan.md.

`run:` is stored raw and expanded once per node at graph build, from that
node's final -- post-override -- parameter values. Before, it was expanded
once per task *definition* at load, which was both stale (no override had
been applied yet) and shared across every node built from that task.

The precedence ladder these tests pin is
`default -> with:/kwargs -> -P -> -D -> --flag`, and it must hold for a
body reference exactly as it does for `node.params`.
"""
import asyncio
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


def _load(tmpdir, flow_dv):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert [m.msg for m in collector.markers] == []
    return pkg


def _body(pkg, tmpdir, task="pkg.t", **builder_kw):
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"), **builder_kw)
    return builder.mkTaskNode(task).task.body


SEED_FLOW = """\
package:
    name: pkg
    tasks:
    - name: t
      shell: bash
      with:
        seed: { type: int, value: 0 }
      run: echo "seed=${{ seed }}"
"""


# ------------------------------------------------------------------ Phase B

def test_body_is_stored_raw(tmpdir):
    pkg = _load(tmpdir, SEED_FLOW)
    assert pkg.task_m["pkg.t"].run.strip() == 'echo "seed=${{ seed }}"'


def test_body_uses_the_default_when_nothing_overrides_it(tmpdir):
    assert "seed=0" in _body(_load(tmpdir, SEED_FLOW), tmpdir)


def test_param_default_that_references_a_package_var(tmpdir):
    """The §2 motivating case. Eagerly expanding `run:` against a *lazily*
    stored param default spliced the raw reference into the shell body, and
    the task failed at execution with `bad substitution` -- no marker, no
    diagnostic."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    with:
      base: { type: str, value: "B" }
    tasks:
    - name: t
      shell: bash
      with:
        a: { type: str, value: "${{ base }}-suffix" }
      run: echo "a=${{ a }}"
""")
    assert "a=B-suffix" in _body(pkg, tmpdir)


def test_two_nodes_of_one_task_type_get_different_bodies(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      shell: bash
      with:
        msg: { type: str, value: "default" }
      run: echo "${{ msg }}"
    - name: A
      uses: Base
      with: { msg: "a" }
    - name: B
      uses: Base
      with: { msg: "b" }
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert 'echo "a"' in builder.mkTaskNode("pkg.A").task.body
    assert 'echo "b"' in builder.mkTaskNode("pkg.B").task.body


def test_rundir_stays_a_run_phase_placeholder(tmpdir):
    """Decision 3: `rundir` resolves at execution, not at build. The node's
    final rundir is not even settled where the body is expanded."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: t
      shell: bash
      run: echo "${{ rundir }}"
""")
    assert "${{ rundir }}" in _body(pkg, tmpdir)


# ------------------------------------------------------------------ Phase C

def test_task_qualified_D_reaches_the_body(tmpdir):
    pkg = _load(tmpdir, SEED_FLOW)
    body = _body(pkg, tmpdir,
                 task_param_overrides={"pkg.t": {"seed": "7"}})
    assert "seed=7" in body


def test_bare_D_reaches_the_body(tmpdir):
    pkg = _load(tmpdir, SEED_FLOW)
    body = _body(pkg, tmpdir, leaf_param_overrides={"seed": "7"})
    assert "seed=7" in body


def test_D_beats_the_declared_default_in_body_and_params_alike(tmpdir):
    """The bug as reported: `dfm.params.json` carried the override while the
    body carried the default. They must not disagree."""
    pkg = _load(tmpdir, SEED_FLOW)
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"),
        task_param_overrides={"pkg.t": {"seed": "7"}})
    node = builder.mkTaskNode("pkg.t")
    assert node.params.seed == 7
    assert "seed=7" in node.task.body


def test_kwargs_reach_the_body(tmpdir):
    pkg = _load(tmpdir, SEED_FLOW)
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert "seed=3" in builder.mkTaskNode("pkg.t", seed=3).task.body


def test_D_beats_kwargs(tmpdir):
    """Decision 4. `kwargs` is how the *description* constructs a node --
    the programmatic equivalent of `with:` -- and `-D` is the user
    overriding the description from outside, so `-D` wins. Before Phase C
    this held only as an artifact of statement order."""
    pkg = _load(tmpdir, SEED_FLOW)
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"),
        task_param_overrides={"pkg.t": {"seed": "7"}})
    node = builder.mkTaskNode("pkg.t", seed=3)
    assert node.params.seed == 7
    assert "seed=7" in node.task.body


def test_unknown_kwarg_is_still_rejected(tmpdir):
    pkg = _load(tmpdir, SEED_FLOW)
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    with pytest.raises(Exception, match="do not include"):
        builder.mkTaskNode("pkg.t", nosuchparam=1)


def test_set_rebind_reaches_the_body(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    with:
      flavor: { type: str, value: vanilla }
    tasks:
    - name: leaf
      shell: bash
      with:
        msg: { type: str, value: "${{ pkg.flavor }}" }
      run: echo "msg=${{ msg }}"
    - name: t
      set:
      - pkg.flavor: chocolate
      body:
      - name: inner
        uses: leaf
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode("pkg.t")
    bodies = [t.task.body for t in node.tasks if getattr(t.task, "body", None)]
    assert any("msg=chocolate" in b for b in bodies), bodies


# ------------------------------------------------------------ end to end CLI

def _dfm(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(cwd), capture_output=True, text=True)


def _ran_body(cwd, task):
    with open(os.path.join(str(cwd), "rundir", task, "%s.log" % task)) as f:
        return f.read()


CLI_FLOW = """\
package:
    name: pkg
    tasks:
    - name: t
      shell: bash
      with:
        seed: { type: int, value: 0, cli: {short: s} }
      run: echo "seed=${{ seed }}"
"""


def test_cli_D_reaches_the_executed_body(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(CLI_FLOW)
    proc = _dfm(tmpdir, "run", "t", "-D", "pkg.t.seed=7")
    assert proc.returncode == 0, proc.stderr
    assert "seed=7" in _ran_body(tmpdir, "pkg.t")


def test_cli_flag_reaches_the_executed_body(tmpdir):
    """A task `--flag` binds through the override map, so it lands on the
    same rung as -D and reaches the body the same way."""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(CLI_FLOW)
    proc = _dfm(tmpdir, "run", "t", "--seed", "42")
    assert proc.returncode == 0, proc.stderr
    assert "seed=42" in _ran_body(tmpdir, "pkg.t")


def test_cli_flag_beats_D_in_the_body(tmpdir):
    """`--seed 42 -D seed=7` -> 42, in the body as well as in the params."""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(CLI_FLOW)
    proc = _dfm(tmpdir, "run", "t", "--seed", "42", "-D", "seed=7")
    assert proc.returncode == 0, proc.stderr
    assert "seed=42" in _ran_body(tmpdir, "pkg.t")


def test_param_file_reaches_the_executed_body(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(CLI_FLOW)
    with open(os.path.join(str(tmpdir), "p.json"), "w") as f:
        f.write('{"tasks": {"pkg.t": {"seed": 11}}}')
    proc = _dfm(tmpdir, "run", "t", "-P", "p.json")
    assert proc.returncode == 0, proc.stderr
    assert "seed=11" in _ran_body(tmpdir, "pkg.t")


def test_D_beats_param_file_in_the_body(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(CLI_FLOW)
    with open(os.path.join(str(tmpdir), "p.json"), "w") as f:
        f.write('{"tasks": {"pkg.t": {"seed": 11}}}')
    proc = _dfm(tmpdir, "run", "t", "-P", "p.json", "-D", "pkg.t.seed=7")
    assert proc.returncode == 0, proc.stderr
    assert "seed=7" in _ran_body(tmpdir, "pkg.t")


# ------------------------------------------------------------------ Phase D

def test_pytask_body_is_expanded_too(tmpdir):
    """Because expansion happens at build rather than in the shell, it is
    uniform across callables: `pytask` gets it for free, where a runtime
    approach would have needed an opt-in per callable."""
    with open(os.path.join(str(tmpdir), "mod.py"), "w") as f:
        f.write("""
from dv_flow.mgr import TaskDataResult

async def Go(ctxt, input):
    return TaskDataResult()
""")
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: t
      shell: pytask
      with:
        modname: { type: str, value: "mod" }
      run: ${{ srcdir }}/${{ modname }}.py::Go
""")
    body = _body(pkg, tmpdir)
    assert body == os.path.join(str(tmpdir), "mod.py") + "::Go"
