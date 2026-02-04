"""Integration tests for jobserver with nested DFM invocations"""
import os
import asyncio
import subprocess
import sys
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from .marker_collector import MarkerCollector


def test_jobserver_propagates_to_subprocess(tmpdir):
    """Test that MAKEFLAGS with jobserver is set in subprocess environment"""
    print(f"DEBUG: tmpdir type: {type(tmpdir)}")
    print(f"DEBUG: tmpdir value: {tmpdir}")
    print(f"DEBUG: tmpdir str: {str(tmpdir)}")
    
    flow_dv = """
package:
  name: foo
  tasks:
  - name: check_env
    shell: pytask
    run: ${{ srcdir }}/check_env.py::CheckEnv
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    # Task that checks for MAKEFLAGS in subprocess
    task_py = '''
import os
import subprocess
from dv_flow.mgr import TaskDataResult

async def CheckEnv(ctxt, input):
    # Check that MAKEFLAGS is set in context environment
    print(f"DEBUG: ctxt.env keys: {list(ctxt.env.keys())[:10]}")
    makeflags = ctxt.env.get('MAKEFLAGS', 'NOT_SET_IN_CTXT')
    print(f"DEBUG: MAKEFLAGS from ctxt.env: {makeflags}")
    with open(os.path.join(ctxt.rundir, "parent_makeflags.txt"), "w") as f:
        f.write(makeflags)
    
    # Run a subprocess and capture its environment
    status = await ctxt.exec(
        ["sh", "-c", "echo $MAKEFLAGS > subprocess_makeflags.txt"],
        logfile="env_check.log"
    )
    
    return TaskDataResult(status=status)
'''
    with open(os.path.join(tmpdir, "check_env.py"), "w") as f:
        f.write(task_py)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    
    print(f"DEBUG: Before TaskSetRunner creation")
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"), nproc=4)
    print(f"DEBUG: After TaskSetRunner creation")
    print(f"DEBUG: Runner has _jobserver: {hasattr(runner, '_jobserver')}")
    print(f"DEBUG: Runner._jobserver: {runner._jobserver}")
    print(f"DEBUG: Runner MAKEFLAGS: {runner.env.get('MAKEFLAGS', 'NOT SET')}")

    task = builder.mkTaskNode("foo.check_env")
    print(f"DEBUG: Task has ctxt: {hasattr(task, 'ctxt')}")
    if hasattr(task, 'ctxt') and task.ctxt:
        print(f"DEBUG: Task ctxt.env MAKEFLAGS before run: {task.ctxt.env.get('MAKEFLAGS', 'NOT SET')}")
    
    output = asyncio.run(runner.run(task))

    assert runner.status == 0
    
    # Verify MAKEFLAGS was set
    rundir = os.path.join(tmpdir, "rundir/foo.check_env")
    with open(os.path.join(rundir, "parent_makeflags.txt"), "r") as f:
        parent_makeflags = f.read().strip()
    
    print(f"DEBUG: parent_makeflags from file: {parent_makeflags}")
    assert "--jobserver-auth=fifo:" in parent_makeflags
    
    # Verify subprocess inherited it
    with open(os.path.join(rundir, "subprocess_makeflags.txt"), "r") as f:
        subprocess_makeflags = f.read().strip()
    
    print(f"DEBUG: subprocess_makeflags from file: {subprocess_makeflags}")
    assert "--jobserver-auth=fifo:" in subprocess_makeflags


def test_nested_dfm_uses_parent_jobserver(tmpdir):
    """Test that nested DFM invocation detects and uses parent's jobserver"""
    # Create a parent flow that will invoke a child dfm
    parent_flow = """
package:
  name: parent
  tasks:
  - name: invoke_child
    shell: pytask
    run: ${{ srcdir }}/invoke_child.py::InvokeChild
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(parent_flow)
    
    # Create a child flow in a subdirectory
    child_dir = os.path.join(tmpdir, "child")
    os.makedirs(child_dir)
    
    child_flow = """
package:
  name: child
  tasks:
  - name: simple
    shell: bash
    run: echo "child task" > output.txt
"""
    with open(os.path.join(child_dir, "flow.dv"), "w") as f:
        f.write(child_flow)
    
    # Parent task that invokes child dfm
    task_py = f'''
import os
import sys
from dv_flow.mgr import TaskDataResult

async def InvokeChild(ctxt, input):
    # Invoke child dfm in subdirectory
    child_dir = os.path.join(r"{tmpdir}", "child")
    
    # Use dfm via python module
    status = await ctxt.exec(
        [sys.executable, "-m", "dv_flow.mgr", "run", "simple"],
        cwd=child_dir,
        logfile="child_dfm.log"
    )
    
    # Check if child created output (in child's rundir)
    child_output = os.path.join(child_dir, "rundir", "child.simple", "output.txt")
    if os.path.exists(child_output):
        with open(child_output, "r") as f:
            content = f.read()
        with open(os.path.join(ctxt.rundir, "child_output.txt"), "w") as f:
            f.write(content)
    
    return TaskDataResult(status=status)
'''
    with open(os.path.join(tmpdir, "invoke_child.py"), "w") as f:
        f.write(task_py)
    
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"), nproc=4)
    
    task = builder.mkTaskNode("parent.invoke_child")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Verify child task ran successfully
    rundir = os.path.join(tmpdir, "rundir/parent.invoke_child")
    assert os.path.exists(os.path.join(rundir, "child_output.txt"))
    
    with open(os.path.join(rundir, "child_output.txt"), "r") as f:
        content = f.read()
    assert "child task" in content


def test_jobserver_respects_nproc_limit(tmpdir):
    """Test that jobserver correctly limits parallel execution"""
    flow_dv = """
package:
  name: foo
  tasks:
"""
    
    # Create 10 tasks that run concurrently
    num_tasks = 10
    for i in range(num_tasks):
        flow_dv += f"""
  - name: task_{i}
    shell: bash
    run: |
      date +%s.%N > start_{i}.txt
      sleep 0.2
      date +%s.%N > end_{i}.txt
"""
    
    # Add a final task that depends on all
    flow_dv += """
  - name: all
    uses: std.Message
    needs: ["""
    flow_dv += ", ".join([f"task_{i}" for i in range(num_tasks)])
    flow_dv += """]
    with:
      msg: "All done"
"""
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    
    # Set nproc to 2 to test limiting
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"), nproc=2)
    
    task = builder.mkTaskNode("foo.all")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    
    # Collect all start times
    start_times = []
    for i in range(num_tasks):
        start_file = os.path.join(tmpdir, f"rundir/foo.task_{i}/start_{i}.txt")
        if os.path.exists(start_file):
            with open(start_file, "r") as f:
                timestamp = float(f.read().strip())
                start_times.append(timestamp)
    
    assert len(start_times) == num_tasks
    
    # With nproc=2, tasks should execute in waves
    # Sort by start time
    start_times.sort()
    
    # Check that not all tasks started at the same time
    # (they should be spread out due to nproc limit)
    first_start = start_times[0]
    last_start = start_times[-1]
    time_span = last_start - first_start
    
    # With 10 tasks and nproc=2, we expect at least 5 waves (2 tasks per wave)
    # Each wave takes ~0.2s, so minimum span should be ~0.8s (4 sequential waves after first)
    assert time_span > 0.5, f"Time span {time_span}s too small for nproc=2 limit"
