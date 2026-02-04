import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_data import TaskDataInput, TaskDataResult
from dv_flow.mgr.util import loadProjPkgDef

def test_run_tasks_single(tmpdir):
    """Test RunTasks with a single TaskRunSpec"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create producer task as Python file
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def Producer(ctxt, input):
    spec = ctxt.mkDataItem(
        type="std.TaskRunSpec",
        task_type="std.Message",
        task_name="dynamic_msg",
        params={"msg": "Hello from dynamic task"}
    )
    return TaskDataResult(status=0, output=[spec])
"""
    
    with open(os.path.join(tmpdir, "producer.py"), "w") as f:
        f.write(producer_py)
    
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: Producer
    shell: pytask
    run: producer.Producer
    
  - name: Execute
    needs: [Producer]
    uses: std.RunTasks
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
    
    task = builder.mkTaskNode("test_pkg.Execute")
    
    result = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert result is not None


def test_run_tasks_multiple(tmpdir, capsys):
    """Test RunTasks with multiple TaskRunSpec items"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create producer task as Python file
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def Producer(ctxt, input):
    specs = []
    for i in range(3):
        spec = ctxt.mkDataItem(
            type="std.TaskRunSpec",
            task_type="std.Message",
            task_name=f"msg_{i}",
            params={"msg": f"Message {i}"}
        )
        specs.append(spec)
    return TaskDataResult(status=0, output=specs)
"""
    
    with open(os.path.join(tmpdir, "producer.py"), "w") as f:
        f.write(producer_py)
    
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: Producer
    shell: pytask
    run: producer.Producer
    
  - name: Execute
    needs: [Producer]
    uses: std.RunTasks
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=4)
    
    task = builder.mkTaskNode("test_pkg.Execute")
    
    result = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Check that all messages were printed
    captured = capsys.readouterr()
    for i in range(3):
        assert f"msg_{i}: Message {i}" in captured.out


def test_run_tasks_with_batch_deps(tmpdir, capsys):
    """Test RunTasks with dependencies between dynamic tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create producer task as Python file
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def Producer(ctxt, input):
    specs = []
    
    # First task
    spec1 = ctxt.mkDataItem(
        type="std.TaskRunSpec",
        task_type="std.Message",
        task_name="msg_first",
        params={"msg": "First message"}
    )
    specs.append(spec1)
    
    # Second task depends on first
    spec2 = ctxt.mkDataItem(
        type="std.TaskRunSpec",
        task_type="std.Message",
        task_name="msg_second",
        params={"msg": "Second message"},
        needs=["msg_first"]
    )
    specs.append(spec2)
    
    return TaskDataResult(status=0, output=specs)
"""
    
    with open(os.path.join(tmpdir, "producer.py"), "w") as f:
        f.write(producer_py)
    
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: Producer
    shell: pytask
    run: producer.Producer
    
  - name: Execute
    needs: [Producer]
    uses: std.RunTasks
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=4)
    
    task = builder.mkTaskNode("test_pkg.Execute")
    
    result = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Check execution order
    captured = capsys.readouterr()
    first_pos = captured.out.find("msg_first: First message")
    second_pos = captured.out.find("msg_second: Second message")
    
    assert first_pos >= 0, "First message not found"
    assert second_pos >= 0, "Second message not found"
    assert first_pos < second_pos, "Messages not in dependency order"


def test_run_tasks_empty_input(tmpdir):
    """Test RunTasks with no TaskRunSpec items (should succeed with no work)"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create producer task as Python file
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def Producer(ctxt, input):
    # Return empty list
    return TaskDataResult(status=0, output=[])
"""
    
    with open(os.path.join(tmpdir, "producer.py"), "w") as f:
        f.write(producer_py)
    
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: Producer
    shell: pytask
    run: producer.Producer
    
  - name: Execute
    needs: [Producer]
    uses: std.RunTasks
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
    
    task = builder.mkTaskNode("test_pkg.Execute")
    
    result = asyncio.run(runner.run(task))
    
    # Should succeed with no work done
    assert runner.status == 0


def test_run_tasks_error_propagation(tmpdir):
    """Test that errors in dynamic tasks propagate correctly (fail-fast)"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create producer task as Python file
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def Producer(ctxt, input):
    spec = ctxt.mkDataItem(
        type="std.TaskRunSpec",
        task_type="test_pkg.FailTask",
        task_name="failing_task"
    )
    return TaskDataResult(status=0, output=[spec])
"""
    
    with open(os.path.join(tmpdir, "producer.py"), "w") as f:
        f.write(producer_py)
    
    # Create failing task
    fail_task_py = """
from dv_flow.mgr.task_data import TaskDataResult

async def FailTask(ctxt, input):
    return TaskDataResult(status=1, output=[])
"""
    
    with open(os.path.join(tmpdir, "fail_task.py"), "w") as f:
        f.write(fail_task_py)
    
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: FailTask
    shell: pytask
    run: fail_task.FailTask
  
  - name: Producer
    shell: pytask
    run: producer.Producer
    
  - name: Execute
    needs: [Producer]
    uses: std.RunTasks
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
    
    task = builder.mkTaskNode("test_pkg.Execute")
    
    result = asyncio.run(runner.run(task))
    
    # Should fail due to dynamic task failure
    assert runner.status != 0
