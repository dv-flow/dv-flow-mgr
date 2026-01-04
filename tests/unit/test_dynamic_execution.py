import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult, TaskDataOutput
from pydantic import BaseModel

class EmptyParams(BaseModel):
    pass

class CounterParams(BaseModel):
    value: int = 0

def test_dynamic_simple_single_task(tmpdir):
    """Test dynamically scheduling a single independent task"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Track execution
    executed = []
    
    async def parent_task(ctxt, input):
        """Parent task that dynamically schedules a child"""
        executed.append("parent")
        
        # Create a dynamic task
        async def child_task(ctxt, input):
            executed.append("child")
            return TaskDataResult(status=0, output=[])
        
        child = TaskNodeLeaf(
            name="dynamic_child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=child_task
        )
        
        # Execute dynamically
        result = await ctxt.run_subgraph(child)
        
        return TaskDataResult(status=0, output=[])
    
    # Create and run parent task
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent = TaskNodeLeaf(
        name="parent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task
    )
    
    runner = TaskSetRunner(rundir=rundir, nproc=2)
    asyncio.run(runner.run(parent))
    
    # Verify execution
    assert "parent" in executed
    assert "child" in executed
    assert runner.status == 0

def test_dynamic_multiple_tasks(tmpdir):
    """Test dynamically scheduling multiple independent tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Track execution
    executed = []
    
    async def parent_task(ctxt, input):
        """Parent task that dynamically schedules multiple children"""
        executed.append("parent")
        
        # Create multiple dynamic tasks
        async def make_child(name):
            async def child_task(ctxt, input):
                executed.append(name)
                return TaskDataResult(status=0, output=[])
            return child_task
        
        children = []
        for i in range(3):
            child_func = await make_child(f"child{i}")
            child = TaskNodeLeaf(
                name=f"dynamic_child_{i}",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=child_func
            )
            children.append(child)
        
        # Execute all dynamically
        results = await ctxt.run_subgraph(children)
        
        assert len(results) == 3
        return TaskDataResult(status=0, output=[])
    
    # Create and run parent task
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent = TaskNodeLeaf(
        name="parent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task
    )
    
    runner = TaskSetRunner(rundir=rundir, nproc=4)
    asyncio.run(runner.run(parent))
    
    # Verify execution
    assert "parent" in executed
    assert "child0" in executed
    assert "child1" in executed
    assert "child2" in executed
    assert runner.status == 0

def test_dynamic_with_dependencies(tmpdir):
    """Test dynamically scheduling tasks with dependencies"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Track execution order
    executed = []
    
    async def parent_task(ctxt, input):
        """Parent task that creates a dependency chain dynamically"""
        executed.append("parent")
        
        # Create tasks with dependencies
        async def task_a(ctxt, input):
            executed.append("task_a")
            return TaskDataResult(status=0, output=[])
        
        async def task_b(ctxt, input):
            # Should run after task_a
            assert "task_a" in executed
            executed.append("task_b")
            return TaskDataResult(status=0, output=[])
        
        node_a = TaskNodeLeaf(
            name="dynamic_a",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_a
        )
        
        node_b = TaskNodeLeaf(
            name="dynamic_b",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_b
        )
        node_b.needs = [(node_a, False)]
        
        # Execute with dependency
        results = await ctxt.run_subgraph([node_a, node_b])
        
        assert len(results) == 2
        return TaskDataResult(status=0, output=[])
    
    # Create and run parent task
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent = TaskNodeLeaf(
        name="parent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task
    )
    
    runner = TaskSetRunner(rundir=rundir, nproc=4)
    asyncio.run(runner.run(parent))
    
    # Verify execution order
    assert executed.index("task_a") < executed.index("task_b")
    assert runner.status == 0

def test_dynamic_respects_nproc(tmpdir):
    """Test that exec calls respect nproc limit"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Track concurrent exec calls
    import threading
    exec_count = 0
    max_concurrent = 0
    lock = threading.Lock()
    
    def on_exec_start():
        nonlocal exec_count, max_concurrent
        with lock:
            exec_count += 1
            if exec_count > max_concurrent:
                max_concurrent = exec_count
    
    def on_exec_end():
        nonlocal exec_count
        with lock:
            exec_count -= 1
    
    async def parent_task(ctxt, input):
        """Parent creates many tasks that call exec"""
        
        # Install callbacks on the context
        ctxt._exec_start_callback = on_exec_start
        ctxt._exec_end_callback = on_exec_end
        
        async def exec_task(ctxt, input):
            # Install callbacks on this context too
            ctxt._exec_start_callback = on_exec_start
            ctxt._exec_end_callback = on_exec_end
            
            # Call exec - this should be gated by semaphore
            await ctxt.exec(['sleep', '0.05'])
            return TaskDataResult(status=0, output=[])
        
        # Create many tasks
        tasks = []
        for i in range(10):
            task = TaskNodeLeaf(
                name=f"exec_task_{i}",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=exec_task
            )
            tasks.append(task)
        
        await ctxt.run_subgraph(tasks)
        return TaskDataResult(status=0, output=[])
    
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent = TaskNodeLeaf(
        name="parent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task
    )
    
    # Run with nproc=2
    runner = TaskSetRunner(rundir=rundir, nproc=2)
    asyncio.run(runner.run(parent))
    
    # Should never exceed nproc for concurrent exec calls
    assert max_concurrent <= 2, f"Expected max_concurrent <= 2, got {max_concurrent}"
    assert runner.status == 0

def test_dynamic_error_propagation(tmpdir):
    """Test that errors in dynamic tasks propagate correctly"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent creates a failing task"""
        
        async def failing_task(ctxt, input):
            return TaskDataResult(status=1, output=[])  # Fail
        
        child = TaskNodeLeaf(
            name="failing_child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=failing_task
        )
        
        await ctxt.run_subgraph(child)
        return TaskDataResult(status=0, output=[])
    
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent = TaskNodeLeaf(
        name="parent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task
    )
    
    runner = TaskSetRunner(rundir=rundir, nproc=2)
    asyncio.run(runner.run(parent))
    
    # Should propagate failure
    assert runner.status != 0
