import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader


def test_subtask_invocation_simple(tmpdir):
    """Test running a sub-task of a compound task"""
    flow_dv = """
package:
    name: foo

    tasks:
    - name: Base
      tasks:
      - name: PrintMessage
        uses: std.Message
        with:
            msg: "Hello World"
    - name: Ext
      uses: Base
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    # Test running Base.PrintMessage directly
    t1 = builder.mkTaskNode("foo.Base.PrintMessage")
    output = asyncio.run(runner.run(t1))
    assert runner.status == 0

    # Test running Ext.PrintMessage (which should resolve to Base.PrintMessage)
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir2"),
        loader=loader)
    runner2 = TaskSetRunner(rundir=os.path.join(rundir, "rundir2"))
    t2 = builder2.mkTaskNode("foo.Ext.PrintMessage")
    output = asyncio.run(runner2.run(t2))
    assert runner2.status == 0


def test_subtask_invocation_with_params(tmpdir):
    """Test running a sub-task with parameter inheritance from parent"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: Base
    with:
      top_msg:
        type: str
        value: "Hello from Base"
    tasks:
    - name: PrintMessage
      uses: std.Message
      with:
          msg: "${{ this.top_msg }}"
  - name: Ext
    uses: Base
    with:
      top_msg: "Hello from Ext"
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    # Test running Ext.PrintMessage (should use "Hello from Ext")
    t1 = builder.mkTaskNode("foo.Ext.PrintMessage")
    output = asyncio.run(runner.run(t1))
    assert runner.status == 0


def test_subtask_api_access(tmpdir):
    """Test accessing sub-tasks via API (PackageLoader.getTask)"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: Base
    tasks:
    - name: SubTask1
      uses: std.Message
      with:
          msg: "SubTask1"
    - name: SubTask2
      uses: std.Message
      with:
          msg: "SubTask2"
  - name: Ext
    uses: Base
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    loader = PackageLoader()
    pkg = loader.load(os.path.join(rundir, "flow.dv"))

    # Test finding Base.SubTask1
    task1 = loader.getTask("foo.Base.SubTask1")
    assert task1 is not None
    assert task1.name == "foo.Base.SubTask1"

    # Test finding Ext.SubTask1 (should resolve to Base.SubTask1)
    task2 = loader.getTask("foo.Ext.SubTask1")
    assert task2 is not None
    assert task2.leafname == "SubTask1"

    # Test finding Ext.SubTask2
    task3 = loader.getTask("foo.Ext.SubTask2")
    assert task3 is not None
    assert task3.leafname == "SubTask2"


def test_nested_subtask_invocation(tmpdir):
    """Test running nested sub-tasks"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: Level1
    tasks:
    - name: Level2
      tasks:
      - name: Level3
        uses: std.Message
        with:
            msg: "Nested task"
  - name: Extended
    uses: Level1
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    # Test running nested sub-task
    t1 = builder.mkTaskNode("foo.Level1.Level2.Level3")
    output = asyncio.run(runner.run(t1))
    assert runner.status == 0

    # Test running nested sub-task through extended task
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir2"),
        loader=loader)
    runner2 = TaskSetRunner(rundir=os.path.join(rundir, "rundir2"))
    t2 = builder2.mkTaskNode("foo.Extended.Level2.Level3")
    output = asyncio.run(runner2.run(t2))
    assert runner2.status == 0
