import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult
from pydantic import BaseModel

class EmptyParams(BaseModel):
    pass

async def simple_task(ctxt, input):
    """Simple task that returns success"""
    return TaskDataResult(status=0, output=[])

def test_run_subgraph_fallback_nested_runner(tmpdir):
    """Test that run_subgraph falls back to nested runner when dynamic disabled"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create a simple runner (dynamic disabled)
    runner = TaskSetRunner(rundir=rundir, nproc=1)
    
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    run_ctxt = TaskRunCtxt(
        runner=runner,
        ctxt=node_ctxt,
        rundir=rundir
    )
    
    # Create a simple task
    task = TaskNodeLeaf(
        name="test_task",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=simple_task
    )
    
    # run_subgraph should fall back to nested runner
    result = asyncio.run(run_ctxt.run_subgraph(task))
    
    # Verify result
    assert result is not None
    assert result.output is not None

def test_run_subgraph_method_exists(tmpdir):
    """Test that TaskRunCtxt has run_subgraph method"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir)
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    run_ctxt = TaskRunCtxt(
        runner=runner,
        ctxt=node_ctxt,
        rundir=rundir
    )
    
    # Check method exists
    assert hasattr(run_ctxt, 'run_subgraph')
    assert callable(run_ctxt.run_subgraph)

def test_run_subgraph_accepts_single_task(tmpdir):
    """Test that run_subgraph accepts a single TaskNode"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir, nproc=1)
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    run_ctxt = TaskRunCtxt(
        runner=runner,
        ctxt=node_ctxt,
        rundir=rundir
    )
    
    task = TaskNodeLeaf(
        name="single_task",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=simple_task
    )
    
    # Should accept single task
    result = asyncio.run(run_ctxt.run_subgraph(task))
    assert result is not None

def test_run_subgraph_accepts_task_list(tmpdir):
    """Test that run_subgraph accepts a list of TaskNodes"""
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir, nproc=1)
    node_ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    run_ctxt = TaskRunCtxt(
        runner=runner,
        ctxt=node_ctxt,
        rundir=rundir
    )
    
    task1 = TaskNodeLeaf(
        name="task1",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=simple_task
    )
    
    task2 = TaskNodeLeaf(
        name="task2",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=node_ctxt,
        task=simple_task
    )
    
    # Should accept list of tasks
    result = asyncio.run(run_ctxt.run_subgraph([task1, task2]))
    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 2
