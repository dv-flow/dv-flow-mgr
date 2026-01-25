"""
End-to-end integration test for caching
"""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.mark.asyncio
async def test_cache_e2e_simple():
    """Test basic cache hit/miss flow with a simple task"""
    from dv_flow.mgr.cache_config import load_cache_providers
    from dv_flow.mgr.ext_rgy import ExtRgy
    from dv_flow.mgr.task_def import TaskDef
    from dv_flow.mgr.task_data import TaskDataInput, TaskDataResult
    from dv_flow.mgr.cache_util import compute_cache_key, check_cache, store_in_cache
    from dv_flow.mgr.cache_provider import CompressionType
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        rundir = Path(tmpdir) / "rundir"
        rundir.mkdir()
        
        # Set up cache environment
        os.environ['DV_FLOW_CACHE'] = str(cache_dir)
        
        try:
            providers = load_cache_providers()
            assert len(providers) == 1
            
            registry = ExtRgy.inst()
            
            # Create a simple task definition with caching enabled
            task_def = TaskDef(
                name='test_task',
                cache=True
            )
            
            # Create some dummy params (simple object)
            class Params:
                value = 42
            
            params = Params()
            
            # First run: cache miss
            cache_key = await compute_cache_key(
                'test_task',
                task_def,
                params,
                [],
                str(rundir),
                registry
            )
            
            assert cache_key is not None
            assert cache_key.startswith('test_task:')
            
            # Check cache (should be miss)
            entry = await check_cache(cache_key, providers)
            assert entry is None
            
            # Store result in cache
            output_template = {'output': [], 'result': 'success'}
            stored = await store_in_cache(
                cache_key,
                output_template,
                None,  # No artifacts
                providers,
                CompressionType.No,
                metadata={'test': 'metadata'}
            )
            
            assert stored
            
            # Second run: cache hit
            entry = await check_cache(cache_key, providers)
            assert entry is not None
            assert entry.key == cache_key
            assert entry.output_template == output_template
            
        finally:
            if 'DV_FLOW_CACHE' in os.environ:
                del os.environ['DV_FLOW_CACHE']


def test_cache_integration_fields():
    """Test that TaskDataResult has cache fields"""
    from dv_flow.mgr.task_data import TaskDataResult
    
    result = TaskDataResult()
    assert hasattr(result, 'cache_hit')
    assert hasattr(result, 'cache_stored')
    assert result.cache_hit == False
    assert result.cache_stored == False
    
    result2 = TaskDataResult(cache_hit=True, cache_stored=False)
    assert result2.cache_hit == True
    assert result2.cache_stored == False


def test_cache_task_runner_fields():
    """Test that TaskSetRunner has cache fields"""
    from dv_flow.mgr.task_runner import TaskSetRunner
    
    runner = TaskSetRunner(rundir="/tmp")
    assert hasattr(runner, 'cache_providers')
    assert hasattr(runner, 'hash_registry')
    assert runner.cache_providers == []
    assert runner.hash_registry is None
