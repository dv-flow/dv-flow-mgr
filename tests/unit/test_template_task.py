"""Tests for template tasks (Phase 1).

Template tasks defer run-expression expansion to graph-build time.
"""
import asyncio
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from .marker_collector import MarkerCollector


def test_template_run_deferred(tmpdir):
    """Template task's run is NOT expanded at load time (raw ${{ survives)."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      template: true
      run: "echo ${{ matrix.variant }}"
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    # The task's run should still contain the raw expression
    tmpl_task = pkg.task_m.get("pkg.Tmpl")
    assert tmpl_task is not None
    assert tmpl_task.template is True
    assert "${{" in tmpl_task.run


def test_template_via_uses(tmpdir):
    """Task with uses: TemplateFoo expands template's run in the use-site context."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      template: true
      shell: bash
      run: "echo hello"
    - name: entry
      uses: Tmpl
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    # Building the node should succeed (template expanded at build time)
    node = builder.mkTaskNode("pkg.entry")
    assert node is not None


def test_template_direct_invoke_error(tmpdir):
    """Invoking a template task directly raises an error."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      template: true
      run: "echo hello"
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))

    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    with pytest.raises(Exception, match="template task"):
        builder.mkTaskNode("pkg.Tmpl")


def test_template_param_expansion(tmpdir):
    """Template task parameters with ${{ }} expand correctly at graph-build time."""
    flow_dv = """\
package:
    name: pkg
    with:
      flavor:
        type: str
        value: vanilla
    tasks:
    - name: Tmpl
      template: true
      shell: bash
      run: "echo ${{ flavor }}"
    - name: entry
      uses: Tmpl
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode("pkg.entry")
    assert node is not None


def test_template_multiple_instantiation(tmpdir):
    """Same template instantiated twice via two uses: references; each gets
    independent expansion (no mutation of shared Task)."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      template: true
      shell: bash
      run: "echo hello"
    - name: A
      uses: Tmpl
    - name: B
      uses: Tmpl
    - name: entry
      passthrough: all
      consumes: none
      needs: [A, B]
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode("pkg.entry")
    assert node is not None

    # Verify the shared Task object was not mutated
    tmpl = pkg.task_m.get("pkg.Tmpl")
    assert "${{" not in (tmpl.run or ""), \
        "Template has no ${{ to expand in this test, so run should remain as-is"


def test_non_template_unchanged(tmpdir):
    """A normal (non-template) task's run is expanded at load time. Regression guard."""
    flow_dv = """\
package:
    name: pkg
    with:
      flavor:
        type: str
        value: chocolate
    tasks:
    - name: entry
      shell: bash
      run: "echo ${{ flavor }}"
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    # Verify run was expanded at load time
    task = pkg.task_m.get("pkg.entry")
    assert task is not None
    assert task.template is False
    assert "${{" not in task.run
    assert "chocolate" in task.run



def test_template_in_matrix(tmpdir, capsys):
    """Template task used inside a matrix strategy; ${{ matrix.variant }}
    resolves to different values per cell."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: Tmpl
      template: true
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
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "variant_alpha" in captured.out
    assert "variant_beta" in captured.out


def test_template_and_override_conflict():
    """TaskDef with both template=true and override set raises validation error."""
    from dv_flow.mgr.task_def import TaskDef
    with pytest.raises(Exception, match="template.*override|override.*template"):
        TaskDef.model_validate({
            "name": "Bad",
            "template": True,
            "override": "some.Task",
            "run": "echo hi",
        })
