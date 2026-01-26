"""Tests for exec_parallel method in TaskRunCtxt"""
import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader, ExecCmd
from dv_flow.mgr.task_runner import TaskSetRunner
from .marker_collector import MarkerCollector


def test_exec_parallel_basic(tmpdir):
    """Test basic parallel execution of multiple commands"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: entry
    shell: pytask
    run: ${{ srcdir }}/parallel_task.py::ParallelTask
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    # Create the task implementation as a plain async function
    task_py = '''
import os
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.task_run_ctxt import ExecCmd

async def ParallelTask(ctxt, input):
    cmds = [
        ExecCmd(cmd=["sh", "-c", "echo file1 > out1.txt"]),
        ExecCmd(cmd=["sh", "-c", "echo file2 > out2.txt"]),
        ExecCmd(cmd=["sh", "-c", "echo file3 > out3.txt"]),
    ]
    statuses = await ctxt.exec_parallel(cmds)
    
    # Write results to verify (use ctxt.rundir)
    with open(os.path.join(ctxt.rundir, "results.txt"), "w") as f:
        f.write(",".join(str(s) for s in statuses))
    
    return TaskDataResult()
'''
    with open(os.path.join(tmpdir, "parallel_task.py"), "w") as f:
        f.write(task_py)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    assert len(marker_collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("foo.entry")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0
    
    # Verify all files were created
    rundir = os.path.join(tmpdir, "rundir/foo.entry")
    assert os.path.isfile(os.path.join(rundir, "out1.txt"))
    assert os.path.isfile(os.path.join(rundir, "out2.txt"))
    assert os.path.isfile(os.path.join(rundir, "out3.txt"))
    
    # Verify statuses
    with open(os.path.join(rundir, "results.txt"), "r") as f:
        results = f.read().strip()
    assert results == "0,0,0"


def test_exec_parallel_with_failures(tmpdir):
    """Test parallel execution where some commands fail"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: entry
    shell: pytask
    run: ${{ srcdir }}/parallel_fail_task.py::ParallelFailTask
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    task_py = '''
import os
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.task_run_ctxt import ExecCmd

async def ParallelFailTask(ctxt, input):
    cmds = [
        ExecCmd(cmd=["sh", "-c", "echo ok > out1.txt; exit 0"]),
        ExecCmd(cmd=["sh", "-c", "exit 1"]),  # This one fails
        ExecCmd(cmd=["sh", "-c", "echo ok > out3.txt; exit 0"]),
    ]
    statuses = await ctxt.exec_parallel(cmds)
    
    with open(os.path.join(ctxt.rundir, "results.txt"), "w") as f:
        f.write(",".join(str(s) for s in statuses))
    
    return TaskDataResult()
'''
    with open(os.path.join(tmpdir, "parallel_fail_task.py"), "w") as f:
        f.write(task_py)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("foo.entry")
    output = asyncio.run(runner.run(task))

    # Verify statuses: first and third succeed (0), second fails (1)
    rundir = os.path.join(tmpdir, "rundir/foo.entry")
    with open(os.path.join(rundir, "results.txt"), "r") as f:
        results = f.read().strip()
    assert results == "0,1,0"


def test_exec_parallel_with_logfiles(tmpdir):
    """Test that custom logfiles are used for each command"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: entry
    shell: pytask
    run: ${{ srcdir }}/parallel_log_task.py::ParallelLogTask
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    task_py = '''
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.task_run_ctxt import ExecCmd

async def ParallelLogTask(ctxt, input):
    cmds = [
        ExecCmd(cmd=["sh", "-c", "echo log1"], logfile="custom1.log"),
        ExecCmd(cmd=["sh", "-c", "echo log2"], logfile="custom2.log"),
    ]
    statuses = await ctxt.exec_parallel(cmds)
    return TaskDataResult()
'''
    with open(os.path.join(tmpdir, "parallel_log_task.py"), "w") as f:
        f.write(task_py)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("foo.entry")
    output = asyncio.run(runner.run(task))

    rundir = os.path.join(tmpdir, "rundir/foo.entry")
    
    # Verify custom log files exist
    assert os.path.isfile(os.path.join(rundir, "custom1.log"))
    assert os.path.isfile(os.path.join(rundir, "custom2.log"))
    
    # Verify log contents
    with open(os.path.join(rundir, "custom1.log"), "r") as f:
        assert "log1" in f.read()
    with open(os.path.join(rundir, "custom2.log"), "r") as f:
        assert "log2" in f.read()


def test_exec_parallel_empty_list(tmpdir):
    """Test parallel execution with empty command list"""
    flow_dv = """
package:
  name: foo
  tasks:
  - name: entry
    shell: pytask
    run: ${{ srcdir }}/parallel_empty_task.py::ParallelEmptyTask
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    task_py = '''
import os
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.task_run_ctxt import ExecCmd

async def ParallelEmptyTask(ctxt, input):
    statuses = await ctxt.exec_parallel([])
    
    with open(os.path.join(ctxt.rundir, "results.txt"), "w") as f:
        f.write(str(len(statuses)))
    
    return TaskDataResult()
'''
    with open(os.path.join(tmpdir, "parallel_empty_task.py"), "w") as f:
        f.write(task_py)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("foo.entry")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0
    
    rundir = os.path.join(tmpdir, "rundir/foo.entry")
    with open(os.path.join(rundir, "results.txt"), "r") as f:
        assert f.read().strip() == "0"
