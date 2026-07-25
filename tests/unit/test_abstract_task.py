"""Successor to test_template_task.py.

`template: true` used to mean two unrelated things: defer `run:` expansion
to graph-build time, and refuse direct invocation. Phase B of
run_body_expansion_plan.md makes deferred expansion how *every* task works,
so the flag is gone; the direct-invocation restriction lives on under the
name that only ever meant that -- `abstract: true`.

Every expansion test here therefore has no flag on it at all. That is the
point: they are the proof that deferral is now universal.
"""
import asyncio
import os

import pytest

from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from .marker_collector import MarkerCollector


def _load(tmpdir, flow_dv):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert [m.msg for m in collector.markers] == []
    return pkg


# ------------------------------------------------------- deferred expansion

def test_run_is_stored_raw(tmpdir):
    """No flag required: the authored body survives load intact."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: T
      run: "echo ${{ matrix.variant }}"
""")
    assert pkg.task_m["pkg.T"].run == "echo ${{ matrix.variant }}"


def test_param_reference_expands_at_graph_build(tmpdir):
    """The case that used to need `template: true`."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    with:
      flavor: { type: str, value: vanilla }
    tasks:
    - name: entry
      shell: bash
      run: "echo ${{ flavor }}"
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert builder.mkTaskNode("pkg.entry").task.body == "echo vanilla"


def test_expansion_does_not_mutate_the_shared_task(tmpdir):
    """Two nodes from one task type must not fight over one body: the Task
    object keeps the template, each node gets its own expansion."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      shell: bash
      with:
        msg: { type: str, value: "default" }
      run: "echo ${{ msg }}"
    - name: A
      uses: Base
      with: { msg: "a" }
    - name: B
      uses: Base
      with: { msg: "b" }
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert builder.mkTaskNode("pkg.A").task.body == "echo a"
    assert builder.mkTaskNode("pkg.B").task.body == "echo b"
    assert pkg.task_m["pkg.Base"].run == "echo ${{ msg }}"


def test_inherited_body_keeps_its_authors_srcdir(tmpdir):
    """`${{ srcdir }}` in a body means where the body was *written*. Under
    load-time expansion that was free; with per-node expansion the binding
    has to be carried along the uses chain."""
    sub = tmpdir.mkdir("sub")
    with open(os.path.join(str(sub), "flow.dv"), "w") as f:
        f.write("""\
package:
    name: p2
    tasks:
    - name: Base
      shell: bash
      run: "echo ${{ srcdir }}"
""")
    pkg = _load(tmpdir, """\
package:
    name: pkg
    imports:
    - sub/flow.dv
    tasks:
    - name: entry
      uses: p2.Base
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert builder.mkTaskNode("pkg.entry").task.body == "echo %s" % str(sub)


def test_matrix_cell_body_reflects_its_own_cell(tmpdir, capsys):
    """One task type, two matrix cells, two different bodies."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      uses: std.Message
      with:
        msg: "variant_${{ this.variant }}"
    - name: MatrixHost
      strategy:
        matrix:
          variant: [alpha, beta]
      body:
      - name: Step
        uses: pkg.Tmpl
    - name: entry
      passthrough: all
      consumes: none
      needs: [MatrixHost]
""")
    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    asyncio.run(runner.run(builder.mkTaskNode("pkg.entry")))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "variant_alpha" in captured.out
    assert "variant_beta" in captured.out


# ----------------------------------------------------------- abstract tasks

def test_abstract_task_via_uses(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      abstract: true
      shell: bash
      run: "echo hello"
    - name: entry
      uses: Base
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    assert builder.mkTaskNode("pkg.entry") is not None


def test_abstract_task_cannot_be_invoked_directly(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      abstract: true
      shell: bash
      run: "echo hello"
""")
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    with pytest.raises(Exception, match="Cannot invoke abstract task"):
        builder.mkTaskNode("pkg.Base")


def test_abstract_and_override_conflict():
    from dv_flow.mgr.task_def import TaskDef
    with pytest.raises(Exception, match="abstract.*override|override.*abstract"):
        TaskDef.model_validate({
            "name": "Bad",
            "abstract": True,
            "override": "some.Task",
            "run": "echo hi",
        })


def test_template_is_no_longer_accepted():
    """The flag is removed, not quietly ignored: TaskDef forbids extras, so
    a stale `template: true` is reported rather than silently doing
    nothing."""
    from dv_flow.mgr.task_def import TaskDef
    with pytest.raises(Exception):
        TaskDef.model_validate({
            "name": "Old",
            "template": True,
            "run": "echo hi",
        })
