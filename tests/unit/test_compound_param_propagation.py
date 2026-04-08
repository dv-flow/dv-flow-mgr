"""
Test that compound task parameters propagate into body tasks.

When a compound task declares a parameter (e.g. 'model') and a body
task references it via ${{ model }}, the expanded value must be visible
to the body task — including when the compound is instantiated via
'uses:' from a matrix strategy with overridden param values.
"""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef
from .marker_collector import MarkerCollector


def test_compound_param_visible_in_body(tmpdir, capsys):
    """Body task can reference enclosing compound task's param via ${{ param }}."""
    flow_dv = """
package:
    name: mypkg

    tasks:
    - name: Greeter
      with:
        greeting:
          type: str
          value: "hello"
      body:
      - name: say
        uses: std.Message
        with:
          msg: "${{ greeting }} world"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None

    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("mypkg.Greeter")
    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    assert "hello world" in captured.out


def test_compound_param_override_via_uses(tmpdir, capsys):
    """Compound param overridden via 'uses:' propagates to body tasks."""
    flow_dv = """
package:
    name: mypkg

    tasks:
    - name: Greeter
      with:
        greeting:
          type: str
          value: "default"
      body:
      - name: say
        uses: std.Message
        with:
          msg: "say ${{ greeting }}"

    - name: CustomGreeter
      uses: Greeter
      with:
        greeting: "howdy"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None

    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("mypkg.CustomGreeter")
    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    assert "say howdy" in captured.out


def test_compound_param_from_matrix_via_uses(tmpdir, capsys):
    """
    Matrix strategy passes value to compound via uses:, body task
    sees the expanded value — reproduces the ioapic reg_smoke_all pattern.
    """
    flow_dv = """
package:
    name: mypkg

    tasks:
    - name: Worker
      with:
        model:
          type: str
      body:
      - name: step
        uses: std.Message
        with:
          msg: "model=${{ model }}"

    - name: RunAll
      strategy:
        matrix:
          model:
          - "alpha"
          - "beta"
      body:
      - name: core
        uses: Worker
        with:
          model: "${{ matrix.model }}"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None

    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("mypkg.RunAll")
    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    assert "model=alpha" in captured.out
    assert "model=beta" in captured.out


def test_compound_param_from_matrix_in_fragment(tmpdir, capsys):
    """Same as above but tasks are in a named fragment."""
    frag_dv = """
fragment:
    name: tests

    tasks:
    - root: Worker
      with:
        model:
          type: str
      body:
      - name: step
        uses: std.Message
        with:
          msg: "model=${{ model }}"

    - root: RunAll
      strategy:
        matrix:
          model:
          - "alpha"
          - "beta"
      body:
      - name: core
        uses: Worker
        with:
          model: "${{ matrix.model }}"
"""

    flow_dv = """
package:
    name: mypkg
    fragments:
    - frag.dv
"""

    with open(os.path.join(tmpdir, "frag.dv"), "w") as f:
        f.write(frag_dv)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(tmpdir, "flow.dv"))

    errors = [m for m in collector.markers if "error" in str(m.severity).lower()]
    assert len(errors) == 0, f"Load errors: {[m.msg for m in errors]}"

    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("mypkg.tests.RunAll")
    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    assert "model=alpha" in captured.out
    assert "model=beta" in captured.out
