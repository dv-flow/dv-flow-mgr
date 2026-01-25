"""
Test cache definition in task schema
"""

import pytest
from dv_flow.mgr.task_def import TaskDef, CacheDef
from dv_flow.mgr.cache_provider import CompressionType


def test_cache_def_defaults():
    """Test CacheDef default values"""
    cache = CacheDef()
    
    assert cache.enabled == True
    assert cache.hash == []
    assert cache.compression == CompressionType.No


def test_cache_def_with_hash_expressions():
    """Test CacheDef with hash expressions"""
    cache = CacheDef(
        enabled=True,
        hash=['shell("gcc --version")', 'env.BUILD_MODE'],
        compression=CompressionType.Gzip
    )
    
    assert cache.enabled
    assert len(cache.hash) == 2
    assert cache.compression == CompressionType.Gzip


def test_task_def_no_cache():
    """Test TaskDef without cache field"""
    task = TaskDef(name='test')
    
    assert task.cache is None


def test_task_def_cache_true():
    """Test TaskDef with cache=True"""
    task = TaskDef(name='test', cache=True)
    
    assert isinstance(task.cache, CacheDef)
    assert task.cache.enabled == True
    assert task.cache.hash == []
    assert task.cache.compression == CompressionType.No


def test_task_def_cache_false():
    """Test TaskDef with cache=False"""
    task = TaskDef(name='test', cache=False)
    
    assert isinstance(task.cache, CacheDef)
    assert task.cache.enabled == False


def test_task_def_cache_custom():
    """Test TaskDef with custom cache configuration"""
    task = TaskDef(
        name='test',
        cache={
            'enabled': True,
            'hash': ['shell("gcc --version")'],
            'compression': 'gzip'
        }
    )
    
    assert isinstance(task.cache, CacheDef)
    assert task.cache.enabled
    assert len(task.cache.hash) == 1
    assert task.cache.compression == CompressionType.Gzip


def test_task_def_cache_disabled():
    """Test TaskDef with cache disabled"""
    task = TaskDef(
        name='test',
        cache={'enabled': False}
    )
    
    assert isinstance(task.cache, CacheDef)
    assert not task.cache.enabled


def test_cache_def_compression_types():
    """Test different compression types"""
    cache_no = CacheDef(compression='no')
    assert cache_no.compression == CompressionType.No
    
    cache_yes = CacheDef(compression='yes')
    assert cache_yes.compression == CompressionType.Yes
    
    cache_gzip = CacheDef(compression='gzip')
    assert cache_gzip.compression == CompressionType.Gzip
    
    cache_bzip2 = CacheDef(compression='bzip2')
    assert cache_bzip2.compression == CompressionType.Bzip2


def test_task_from_yaml_style_dict():
    """Test creating TaskDef from YAML-style dict with cache"""
    task_dict = {
        'name': 'build',
        'run': 'make all',
        'cache': {
            'enabled': True,
            'hash': ['shell("gcc --version")', 'env.CFLAGS'],
            'compression': 'gzip'
        }
    }
    
    task = TaskDef(**task_dict)
    
    assert task.name == 'build'
    assert task.run == 'make all'
    assert isinstance(task.cache, CacheDef)
    assert task.cache.enabled
    assert len(task.cache.hash) == 2
    assert task.cache.compression == CompressionType.Gzip


def test_cache_extra_fields_forbidden():
    """Test that extra fields in CacheDef are rejected"""
    with pytest.raises(Exception):  # Pydantic validation error
        CacheDef(
            enabled=True,
            invalid_field='value'
        )


def test_task_def_cache_with_empty_dict():
    """Test TaskDef with cache as empty dict (uses defaults)"""
    task = TaskDef(name='test', cache={})
    
    assert isinstance(task.cache, CacheDef)
    assert task.cache.enabled == True  # Default
    assert task.cache.hash == []  # Default
    assert task.cache.compression == CompressionType.No  # Default
