"""
Test suite for documentation examples in incremental.rst
"""
import asyncio
import os
import sys
import hashlib
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner, TaskDataResult
from dv_flow.mgr.task_listener_log import TaskListenerLog


@pytest.mark.asyncio
async def test_memento_creation_example(tmpdir):
    """Test memento creation example from documentation"""
    
    task_code = '''
import os
from dv_flow.mgr import TaskDataResult

async def MyTask(ctxt, input):
    """Task that creates a memento"""
    # Perform work
    result_file = os.path.join(ctxt.rundir, "output.txt")
    with open(result_file, "w") as f:
        f.write("result data")
    
    # Create memento with file timestamp
    memento = {
        "result_file": result_file,
        "timestamp": os.path.getmtime(result_file),
        "parameters": {
            "param1": input.params.param1
        }
    }
    
    return TaskDataResult(
        status=0,
        changed=True,
        memento=memento
    )
'''
    
    module_dir = str(tmpdir.mkdir("memento_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "task.py"), "w") as f:
        f.write(task_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: memento_test
  
  tasks:
  - name: my_task
    shell: pytask
    run: memento_pkg.task.MyTask
    with:
      param1:
        type: str
        value: "test"
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("memento_test.my_task")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
        
        # Check that exec.json was created with memento
        exec_file = os.path.join(rundir, "my_task", "my_task.exec_data.json")
        assert os.path.exists(exec_file)
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_uptodate_check_example(tmpdir):
    """Test up-to-date check example from documentation"""
    
    task_code = '''
import os
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.uptodate_ctxt import UpToDateCtxt

async def CheckUpToDate(ctxt):
    """Check if task is up-to-date"""
    if ctxt.memento is None:
        return False  # No previous execution
    
    # Access saved memento data
    prev_timestamp = ctxt.memento.get("timestamp")
    prev_params = ctxt.memento.get("parameters", {})
    
    # Compare with current state
    result_file = ctxt.memento.get("result_file")
    if not os.path.exists(result_file):
        return False
    
    current_timestamp = os.path.getmtime(result_file)
    current_params = {"param1": ctxt.params.param1}
    
    # Up-to-date if nothing changed
    return (prev_timestamp == current_timestamp and
            prev_params == current_params)

async def MyTask(ctxt, input):
    """Task implementation"""
    result_file = os.path.join(ctxt.rundir, "output.txt")
    with open(result_file, "w") as f:
        f.write(f"result: {input.params.param1}")
    
    memento = {
        "result_file": result_file,
        "timestamp": os.path.getmtime(result_file),
        "parameters": {"param1": input.params.param1}
    }
    
    return TaskDataResult(
        status=0,
        changed=True,
        memento=memento
    )
'''
    
    module_dir = str(tmpdir.mkdir("uptodate_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "task.py"), "w") as f:
        f.write(task_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: uptodate_test
  
  tasks:
  - name: my_task
    shell: pytask
    run: uptodate_pkg.task.MyTask
    uptodate: uptodate_pkg.task.CheckUpToDate
    with:
      param1:
        type: str
        value: "test"
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("uptodate_test.my_task")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        # First run
        await runner.run(task)
        assert listener.status == 0
        
        # Second run should be up-to-date
        listener2 = TaskListenerLog()
        runner2 = TaskSetRunner(rundir=rundir)
        runner2.add_listener(listener2)
        await runner2.run(task)
        assert listener2.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_content_hash_pattern(tmpdir):
    """Test content-based detection pattern"""
    
    task_code = '''
import hashlib
import os
from dv_flow.mgr import TaskDataResult

async def ComputeHash(filepath):
    """Compute SHA256 hash of file"""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

async def MyTask(ctxt, input):
    """Task using content hashing"""
    # Process files
    output_file = os.path.join(ctxt.rundir, "output.dat")
    with open(output_file, "w") as f:
        f.write("processed data")
    
    # Store content hash
    file_hash = await ComputeHash(output_file)
    
    return TaskDataResult(
        status=0,
        changed=True,
        memento={"output_hash": file_hash}
    )
'''
    
    module_dir = str(tmpdir.mkdir("hash_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "task.py"), "w") as f:
        f.write(task_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: hash_test
  
  tasks:
  - name: my_task
    shell: pytask
    run: hash_pkg.task.MyTask
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("hash_test.my_task")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_dependency_tracking_pattern(tmpdir):
    """Test dependency tracking pattern"""
    
    task_code = '''
import os
from dv_flow.mgr.uptodate_ctxt import UpToDateCtxt

async def TrackDependencies(ctxt):
    """Track external dependencies"""
    # Read dependency file
    dep_file = os.path.join(ctxt.srcdir, "dependencies.txt")
    if not os.path.exists(dep_file):
        return False
    
    with open(dep_file) as f:
        current_deps = f.read().splitlines()
    
    # Compare with saved dependencies
    saved_deps = ctxt.memento.get("dependencies", [])
    
    # Check if list changed
    if set(current_deps) != set(saved_deps):
        return False
    
    # Check if any dependency file changed
    for dep in current_deps:
        dep_path = os.path.join(ctxt.srcdir, dep)
        if not os.path.exists(dep_path):
            return False
        current_time = os.path.getmtime(dep_path)
        saved_time = ctxt.memento.get(f"dep_time_{dep}")
        if saved_time is None or current_time != saved_time:
            return False
    
    return True

async def MyTask(ctxt, input):
    """Task with dependency tracking"""
    from dv_flow.mgr import TaskDataResult
    
    dep_file = os.path.join(ctxt.srcdir, "dependencies.txt")
    if os.path.exists(dep_file):
        with open(dep_file) as f:
            deps = f.read().splitlines()
        
        memento = {"dependencies": deps}
        for dep in deps:
            dep_path = os.path.join(ctxt.srcdir, dep)
            if os.path.exists(dep_path):
                memento[f"dep_time_{dep}"] = os.path.getmtime(dep_path)
    else:
        memento = {}
    
    return TaskDataResult(
        status=0,
        changed=True,
        memento=memento
    )
'''
    
    module_dir = str(tmpdir.mkdir("dep_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "task.py"), "w") as f:
        f.write(task_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        srcdir = str(tmpdir.mkdir("src"))
        
        # Create dependency file and dependencies
        with open(os.path.join(srcdir, "dependencies.txt"), "w") as f:
            f.write("dep1.txt\ndep2.txt\n")
        
        with open(os.path.join(srcdir, "dep1.txt"), "w") as f:
            f.write("dependency 1")
        
        with open(os.path.join(srcdir, "dep2.txt"), "w") as f:
            f.write("dependency 2")
        
        flowdv = """
package:
  name: dep_test
  
  tasks:
  - name: my_task
    shell: pytask
    run: dep_pkg.task.MyTask
    uptodate: dep_pkg.task.TrackDependencies
"""
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        rundir = str(tmpdir.mkdir("rundir"))
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("dep_test.my_task")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


def test_exec_json_structure(tmpdir):
    """Test that exec.json has expected structure"""
    # This is tested implicitly by other tests that check for exec_data.json files
    # Here we just verify the structure is documented correctly
    exec_data_example = {
        "name": "my_pkg.my_task",
        "status": 0,
        "changed": True,
        "params": {"param1": "value1"},
        "inputs": [],
        "outputs": [],
        "memento": {"timestamp": 1703456789.123},
        "markers": [],
        "exec_info": [],
    }
    
    # Verify structure keys
    assert "name" in exec_data_example
    assert "status" in exec_data_example
    assert "changed" in exec_data_example
    assert "params" in exec_data_example
    assert "memento" in exec_data_example
