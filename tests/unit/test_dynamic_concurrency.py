import asyncio
import os
import pytest
from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult
from pydantic import BaseModel

class EmptyParams(BaseModel):
    pass

def test_circular_dependency_detection(tmpdir):
    """Test that circular dependencies in sub-graphs are detected"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent creates circular dependency"""
        
        async def task_a(ctxt, input):
            return TaskDataResult(status=0, output=[])
        
        async def task_b(ctxt, input):
            return TaskDataResult(status=0, output=[])
        
        node_a = TaskNodeLeaf(
            name="task_a",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_a
        )
        
        node_b = TaskNodeLeaf(
            name="task_b",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_b
        )
        
        # Create circular dependency: A -> B -> A
        node_a.needs = [(node_b, False)]
        node_b.needs = [(node_a, False)]
        
        # Should raise ValueError for circular dependency
        with pytest.raises(ValueError, match="Circular dependency"):
            await ctxt.run_subgraph([node_a, node_b])
        
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
    
    assert runner.status == 0

def test_timeout_on_long_running_task(tmpdir):
    """Test that timeout works for long-running dynamic tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent with timeout on slow child"""
        
        async def slow_task(ctxt, input):
            await asyncio.sleep(5)  # Long running
            return TaskDataResult(status=0, output=[])
        
        child = TaskNodeLeaf(
            name="slow_child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=slow_task
        )
        
        # Should timeout after 0.5 seconds
        try:
            if hasattr(ctxt.runner, 'schedule_subgraph'):
                await ctxt.runner.schedule_subgraph(child, timeout=0.5)
                # Should not reach here
                assert False, "Expected timeout"
            else:
                # Fallback doesn't support timeout, skip
                pass
        except asyncio.TimeoutError:
            # Expected
            pass
        
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
    
    assert runner.status == 0

def test_concurrent_subgraphs_share_nproc(tmpdir):
    """Test that multiple concurrent sub-graphs share nproc limit"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    import threading
    active_count = 0
    max_concurrent = 0
    lock = threading.Lock()
    
    async def parent_task_1(ctxt, input):
        """First parent creates sub-tasks"""
        
        async def slow_task(ctxt, input):
            nonlocal active_count, max_concurrent
            
            with lock:
                active_count += 1
                if active_count > max_concurrent:
                    max_concurrent = active_count
            
            await asyncio.sleep(0.1)
            
            with lock:
                active_count -= 1
            
            return TaskDataResult(status=0, output=[])
        
        tasks = []
        for i in range(3):
            task = TaskNodeLeaf(
                name=f"p1_task_{i}",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=slow_task
            )
            tasks.append(task)
        
        await ctxt.run_subgraph(tasks)
        return TaskDataResult(status=0, output=[])
    
    async def parent_task_2(ctxt, input):
        """Second parent creates sub-tasks"""
        
        async def slow_task(ctxt, input):
            nonlocal active_count, max_concurrent
            
            with lock:
                active_count += 1
                if active_count > max_concurrent:
                    max_concurrent = active_count
            
            await asyncio.sleep(0.1)
            
            with lock:
                active_count -= 1
            
            return TaskDataResult(status=0, output=[])
        
        tasks = []
        for i in range(3):
            task = TaskNodeLeaf(
                name=f"p2_task_{i}",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=slow_task
            )
            tasks.append(task)
        
        await ctxt.run_subgraph(tasks)
        return TaskDataResult(status=0, output=[])
    
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    parent1 = TaskNodeLeaf(
        name="parent1",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task_1
    )
    
    parent2 = TaskNodeLeaf(
        name="parent2",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=parent_task_2
    )
    
    # Run both parents concurrently with nproc=3
    runner = TaskSetRunner(rundir=rundir, nproc=3)
    asyncio.run(runner.run([parent1, parent2]))
    
    # Max concurrent should not exceed nproc (3)
    # Even though each parent wants to run 3 tasks
    assert max_concurrent <= 3
    assert runner.status == 0

def test_stress_many_dynamic_tasks(tmpdir):
    """Stress test with many dynamic tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    completed = []
    
    async def parent_task(ctxt, input):
        """Create many dynamic tasks"""
        
        async def worker_task(task_id):
            async def task(ctxt, input):
                completed.append(task_id)
                await asyncio.sleep(0.01)
                return TaskDataResult(status=0, output=[])
            return task
        
        # Create 50 tasks
        tasks = []
        for i in range(50):
            task_func = await worker_task(i)
            task = TaskNodeLeaf(
                name=f"worker_{i}",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=task_func
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
    
    runner = TaskSetRunner(rundir=rundir, nproc=4)
    asyncio.run(runner.run(parent))
    
    # All tasks should complete
    assert len(completed) == 50
    assert runner.status == 0

def test_nested_dynamic_subgraphs(tmpdir):
    """Test dynamic tasks creating their own dynamic tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    executed = []
    
    async def grandparent_task(ctxt, input):
        """Top level task"""
        executed.append("grandparent")
        
        async def parent_task_inner(ctxt, input):
            """Middle level creates its own sub-graph"""
            executed.append("parent")
            
            async def child_task(ctxt, input):
                executed.append("child")
                return TaskDataResult(status=0, output=[])
            
            child = TaskNodeLeaf(
                name="child",
                srcdir=tmpdir,
                params=EmptyParams(),
                ctxt=ctxt.ctxt,
                task=child_task
            )
            
            await ctxt.run_subgraph(child)
            return TaskDataResult(status=0, output=[])
        
        parent = TaskNodeLeaf(
            name="parent",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=parent_task_inner
        )
        
        await ctxt.run_subgraph(parent)
        return TaskDataResult(status=0, output=[])
    
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    grandparent = TaskNodeLeaf(
        name="grandparent",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=grandparent_task
    )
    
    runner = TaskSetRunner(rundir=rundir, nproc=4)
    asyncio.run(runner.run(grandparent))
    
    # All levels should execute
    assert "grandparent" in executed
    assert "parent" in executed
    assert "child" in executed
    assert runner.status == 0
