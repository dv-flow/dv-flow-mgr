import asyncio
"""
Test cache utility functions
"""

import pytest
import tempfile
from pathlib import Path
from dv_flow.mgr.cache_util import (
    compute_cache_key,
    check_cache,
    store_in_cache,
    validate_output_paths,
    convert_output_to_template
)
from dv_flow.mgr.cache_provider import CacheEntry, CompressionType
from dv_flow.mgr.cache_provider_dir import DirectoryCacheProvider
from dv_flow.mgr.fileset import FileSet
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.task_def import TaskDef


@pytest.fixture
def temp_dir():
    """Create a temporary directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_compute_cache_key_no_cache(temp_dir):
    async def _impl():
        """Test cache key computation for task without cache config"""
        task = TaskDef(name='test')
        registry = ExtRgy.inst()
        
        key = await compute_cache_key(
            'test',
            task,
            None,
            [],
            str(temp_dir),
            registry
        )
        
        assert key is None
    asyncio.run(_impl())

def test_compute_cache_key_disabled(temp_dir):
    async def _impl():
        """Test cache key computation for task with caching disabled"""
        task = TaskDef(name='test', cache={'enabled': False})
        registry = ExtRgy.inst()
        
        key = await compute_cache_key(
            'test',
            task,
            None,
            [],
            str(temp_dir),
            registry
        )
        
        assert key is None
    asyncio.run(_impl())

def test_compute_cache_key_enabled(temp_dir):
    async def _impl():
        """Test cache key computation for task with caching enabled"""
        task = TaskDef(name='test', cache=True)
        registry = ExtRgy.inst()
        
        key = await compute_cache_key(
            'test',
            task,
            None,
            [],
            str(temp_dir),
            registry
        )
        
        assert key is not None
        assert key.startswith('test:')
        assert len(key.split(':')[1]) == 32  # MD5 hash
    asyncio.run(_impl())

def test_check_cache_miss(temp_dir):
    async def _impl():
        """Test cache check with no providers"""
        entry = await check_cache('test:abc123', [])
        assert entry is None
    asyncio.run(_impl())

def test_check_cache_hit(temp_dir):
    async def _impl():
        """Test cache check with existing entry"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        # Store an entry
        entry = CacheEntry(
            key='test:abc123',
            output_template={'result': 'ok'},
            metadata={}
        )
        await provider.put('test:abc123', entry)
        
        # Check cache
        found = await check_cache('test:abc123', [provider])
        assert found is not None
        assert found.key == 'test:abc123'
    asyncio.run(_impl())

def test_store_in_cache_no_artifacts(temp_dir):
    async def _impl():
        """Test storing cache entry without artifacts"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        success = await store_in_cache(
            'test:abc123',
            {'output': []},
            None,
            [provider],
            CompressionType.No
        )
        
        assert success
        
        # Verify stored
        entry = await provider.get('test:abc123')
        assert entry is not None
    asyncio.run(_impl())

def test_store_in_cache_with_artifacts(temp_dir):
    async def _impl():
        """Test storing cache entry with artifacts"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        # Create artifacts
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "file1.txt").write_text("content")
        
        success = await store_in_cache(
            'test:abc123',
            {'output': []},
            artifacts_dir,
            [provider],
            CompressionType.No
        )
        
        assert success
        
        # Verify stored with artifacts
        entry = await provider.get('test:abc123')
        assert entry is not None
        assert entry.artifacts_path == "artifacts"
    asyncio.run(_impl())

def test_validate_output_paths_valid(temp_dir):
    """Test validating output paths within rundir"""
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir / "subdir"),
        files=['test.txt']
    )
    
    valid = validate_output_paths([fileset], str(temp_dir))
    assert valid


def test_validate_output_paths_outside_rundir(temp_dir):
    """Test validating output paths outside rundir"""
    fileset = FileSet(
        filetype='text',
        basedir='/tmp/elsewhere',
        files=['test.txt']
    )
    
    valid = validate_output_paths([fileset], str(temp_dir))
    assert not valid


def test_convert_output_to_template(temp_dir):
    """Test converting output to template with rundir placeholder"""
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir / "output"),
        files=['test.txt']
    )
    
    template = convert_output_to_template([fileset], str(temp_dir))
    
    assert 'output' in template
    assert len(template['output']) == 1
    assert '${{ rundir }}' in template['output'][0]['basedir']


def test_convert_output_to_template_relative_path(temp_dir):
    """Test converting output with relative basedir"""
    fileset = FileSet(
        filetype='text',
        basedir='output',
        files=['test.txt']
    )
    
    template = convert_output_to_template([fileset], str(temp_dir))
    
    assert 'output' in template
    assert len(template['output']) == 1
    # Relative paths should remain as-is
    assert template['output'][0]['basedir'] == 'output'
