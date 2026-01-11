import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef

def test_matrix_basic(tmpdir, capsys):
    """Test basic matrix strategy with 2x2 matrix"""
    flow_dv = """
package:
    name: foo
    tasks:
    - name: MatrixTest
      strategy:
        matrix:
          letter: ["a", "b"]
          number: [1, 2]
      body:
      - name: Task
        uses: std.Message
        with:
          msg: "${{ this.letter }}_${{ this.number }}"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")

    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("foo.MatrixTest")

    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    print("Captured:\n%s\n" % captured.out)
    
    # Should have 4 messages (2x2 matrix)
    assert "a_1" in captured.out
    assert "a_2" in captured.out
    assert "b_1" in captured.out
    assert "b_2" in captured.out

def test_matrix_3x3(tmpdir, capsys):
    """Test 3x3 matrix strategy like PoemGen"""
    flow_dv = """
package:
    name: foo
    tasks:
    - name: MatrixTest
      strategy:
        matrix:
          topic: ["cowboys", "coders", "bartenders"]
          kind: ["sea shanty", "limeric", "ballad"]
      body:
      - name: Task
        uses: std.Message
        with:
          msg: "${{ this.topic }}_${{ this.kind }}"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")

    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("foo.MatrixTest")

    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    print("Captured:\n%s\n" % captured.out)
    
    # Should have 9 messages (3x3 matrix)
    for topic in ["cowboys", "coders", "bartenders"]:
        for kind in ["sea shanty", "limeric", "ballad"]:
            assert f"{topic}_{kind}" in captured.out

def test_matrix_single_var(tmpdir, capsys):
    """Test matrix strategy with single variable"""
    flow_dv = """
package:
    name: foo
    tasks:
    - name: MatrixTest
      strategy:
        matrix:
          value: [1, 2, 3]
      body:
      - name: Task
        uses: std.Message
        with:
          msg: "Value: ${{ this.value }}"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")

    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("foo.MatrixTest")

    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    print("Captured:\n%s\n" % captured.out)
    
    # Should have 3 messages
    assert "Value: 1" in captured.out
    assert "Value: 2" in captured.out
    assert "Value: 3" in captured.out
