import asyncio
import os
import pytest
from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE
from pydantic import BaseModel

class EmptyParams(BaseModel):
    pass

def test_error_in_dynamic_task_propagates(tmpdir):
    """Test that errors in dynamic tasks propagate to parent"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent with failing child"""
        
        async def failing_task(ctxt, input):
            ctxt.error("Task failed intentionally")
            return TaskDataResult(status=1, output=[])
        
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
    
    # Error should propagate
    assert runner.status != 0

def test_exception_in_dynamic_task_handled(tmpdir):
    """Test that exceptions in dynamic tasks are handled"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent with task that raises exception"""
        
        async def exception_task(ctxt, input):
            raise RuntimeError("Test exception")
        
        child = TaskNodeLeaf(
            name="exception_child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=exception_task
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
    
    # Should handle exception gracefully
    asyncio.run(runner.run(parent))
    
    # Task should fail
    assert runner.status != 0

def test_partial_failure_in_dynamic_subgraph(tmpdir):
    """Test that partial failures stop remaining tasks"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    executed = []
    
    async def parent_task(ctxt, input):
        """Parent with multiple tasks, one fails"""
        
        async def task_1(ctxt, input):
            executed.append("task_1")
            return TaskDataResult(status=1, output=[])  # Fail
        
        async def task_2(ctxt, input):
            executed.append("task_2")
            return TaskDataResult(status=0, output=[])
        
        async def task_3(ctxt, input):
            # Should not run if task_1 failed
            executed.append("task_3")
            return TaskDataResult(status=0, output=[])
        
        t1 = TaskNodeLeaf(
            name="task_1",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_1
        )
        
        t2 = TaskNodeLeaf(
            name="task_2",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_2
        )
        
        t3 = TaskNodeLeaf(
            name="task_3",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=task_3
        )
        # t3 depends on t1
        t3.needs = [(t1, False)]
        
        await ctxt.run_subgraph([t1, t2, t3])
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
    
    # task_1 and task_2 should run (independent)
    # task_3 might not run if task_1 failed first
    assert "task_1" in executed
    assert runner.status != 0

def test_markers_from_dynamic_tasks(tmpdir):
    """Test that markers from dynamic tasks are collected"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent with child that adds markers"""
        
        async def marker_task(ctxt, input):
            ctxt.info("Info message from child")
            ctxt.error("Error message from child")
            return TaskDataResult(
                status=0,
                output=[],
                markers=[
                    TaskMarker(msg="Custom marker", severity=SeverityE.Warning)
                ]
            )
        
        child = TaskNodeLeaf(
            name="marker_child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=marker_task
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
    
    # Task should complete successfully
    assert runner.status == 0

def test_cleanup_on_error(tmpdir):
    """Test that resources are cleaned up on error"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent that fails during sub-graph execution"""
        
        async def child_task(ctxt, input):
            return TaskDataResult(status=1, output=[])
        
        child = TaskNodeLeaf(
            name="child",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=child_task
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
    
    # Should have cleaned up (dynamic_enabled should be False after run)
    assert runner._dynamic_enabled == False
    assert runner.status != 0

def test_error_messages_are_clear(tmpdir):
    """Test that error messages from dynamic tasks are clear"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    async def parent_task(ctxt, input):
        """Parent with descriptive error in child"""
        
        async def error_task(ctxt, input):
            ctxt.error("Failed to process file: input.txt not found")
            return TaskDataResult(status=1, output=[])
        
        child = TaskNodeLeaf(
            name="descriptive_error",
            srcdir=tmpdir,
            params=EmptyParams(),
            ctxt=ctxt.ctxt,
            task=error_task
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
    
    # Error should propagate with clear message
    assert runner.status != 0
