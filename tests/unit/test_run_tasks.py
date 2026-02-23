import asyncio
import os
import sys
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_data import TaskDataInput, TaskDataResult
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.ext_rgy import ExtRgy


@pytest.fixture(autouse=True)
def reset_extrgy():
    """Reset the ExtRgy singleton, sys.modules, sys.path, and MAKEFLAGS before each test to prevent state leakage"""
    # Save original sys.modules keys and sys.path
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    
    # Clear MAKEFLAGS to avoid jobserver issues - don't save/restore it
    # because the jobserver FIFO may not exist anymore
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']
    
    # Reset the singleton instance
    ExtRgy._inst = None
    yield
    # Clean up after test
    ExtRgy._inst = None
    
    # Remove any modules that were added during the test
    added_modules = set(sys.modules.keys()) - original_modules
    for mod_name in added_modules:
        del sys.modules[mod_name]
    
    # Restore sys.path
    sys.path[:] = original_path
    
    # Clear MAKEFLAGS again after test to prevent FIFO references from leaking
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']


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


def test_run_tasks_multiple(tmpdir):
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
  name: test_pkg_multiple
  
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
    
    task = builder.mkTaskNode("test_pkg_multiple.Execute")
    
    result = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Check that all tasks were executed
    assert result is not None
    assert len(result.output) == 3, f"Expected 3 tasks, got {len(result.output)}"
    
    # Verify each task was created with correct params
    task_names = {item.task_name for item in result.output}
    assert task_names == {"msg_0", "msg_1", "msg_2"}, f"Unexpected task names: {task_names}"
    
    for item in result.output:
        assert item.task_type == "std.Message"
        assert "msg" in item.params


def test_run_tasks_with_batch_deps(tmpdir):
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
  name: test_pkg_batch_deps
  
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
    
    task = builder.mkTaskNode("test_pkg_batch_deps.Execute")
    
    result = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Verify both tasks were created
    assert result is not None
    assert len(result.output) == 2, f"Expected 2 tasks, got {len(result.output)}"
    
    # Verify dependency is set correctly
    task_by_name = {item.task_name: item for item in result.output}
    assert "msg_first" in task_by_name
    assert "msg_second" in task_by_name
    
    # Check that msg_second depends on msg_first
    msg_second = task_by_name["msg_second"]
    assert "msg_first" in msg_second.needs, f"msg_second should depend on msg_first, but needs={msg_second.needs}"


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
        task_type="test_pkg_error.FailTask",
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
  name: test_pkg_error
  
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
    
    task = builder.mkTaskNode("test_pkg_error.Execute")
    
    result = asyncio.run(runner.run(task))
    
    # Should fail due to dynamic task failure
    assert runner.status != 0
