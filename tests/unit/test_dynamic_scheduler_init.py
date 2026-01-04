import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.dynamic_scheduler import DynamicScheduler

def test_dynamic_scheduler_mixin_initialization(tmpdir):
    """Test that DynamicScheduler mixin initializes correctly"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir)
    
    # Check that dynamic scheduler attributes exist
    assert hasattr(runner, '_dynamic_enabled')
    assert hasattr(runner, '_pending_tasks')
    assert hasattr(runner, '_task_completion_events')
    assert hasattr(runner, '_dynamic_task_queue')
    assert hasattr(runner, '_active_subgraphs')
    assert hasattr(runner, '_subgraph_id_counter')
    
    # Check initial state
    assert runner._dynamic_enabled == False
    assert len(runner._pending_tasks) == 0
    assert len(runner._task_completion_events) == 0
    assert runner._dynamic_task_queue is not None
    assert len(runner._active_subgraphs) == 0
    assert runner._subgraph_id_counter == 0

def test_dynamic_scheduler_disabled_by_default(tmpdir):
    """Test that dynamic scheduling is disabled by default"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir)
    
    assert runner._dynamic_enabled == False
    
    # Attempting to schedule should raise RuntimeError
    from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
    from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
    from pydantic import BaseModel
    
    class EmptyParams(BaseModel):
        pass
    
    async def dummy_task(ctxt, input):
        from dv_flow.mgr.task_data import TaskDataResult
        return TaskDataResult()
    
    ctxt = TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=rundir,
        env=os.environ.copy()
    )
    
    task = TaskNodeLeaf(
        name="test",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=dummy_task
    )
    
    # Should raise RuntimeError because dynamic scheduling is disabled
    with pytest.raises(RuntimeError, match="Dynamic scheduling not enabled"):
        asyncio.run(runner.schedule_subgraph(task))

def test_dynamic_scheduler_inheritance(tmpdir):
    """Test that TaskSetRunner properly inherits from DynamicScheduler"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir)
    
    # Check inheritance
    assert isinstance(runner, DynamicScheduler)
    
    # Check that methods are available
    assert hasattr(runner, 'schedule_subgraph')
    assert callable(runner.schedule_subgraph)
    assert hasattr(runner, '_buildDepMapForSubgraph')
    assert callable(runner._buildDepMapForSubgraph)
    assert hasattr(runner, '_complete_subgraph')
    assert callable(runner._complete_subgraph)

def test_dynamic_scheduler_logger_initialized(tmpdir):
    """Test that dynamic scheduler logger is initialized"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    runner = TaskSetRunner(rundir=rundir)
    
    # Check logger exists
    assert hasattr(runner, '_dynamic_log')
    assert runner._dynamic_log is not None
    assert runner._dynamic_log.name == "DynamicScheduler"
