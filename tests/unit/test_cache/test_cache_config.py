"""
Test cache configuration loading
"""

import pytest
import tempfile
import os
from pathlib import Path
from dv_flow.mgr.cache_config import load_cache_providers, load_cache_config_file
from dv_flow.mgr.cache_provider_dir import DirectoryCacheProvider


@pytest.fixture
def temp_dir():
    """Create a temporary directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_no_cache_env_variable():
    """Test with no DV_FLOW_CACHE set"""
    old_env = os.environ.get('DV_FLOW_CACHE')
    try:
        if 'DV_FLOW_CACHE' in os.environ:
            del os.environ['DV_FLOW_CACHE']
        
        providers = load_cache_providers()
        assert providers == []
    finally:
        if old_env:
            os.environ['DV_FLOW_CACHE'] = old_env


def test_cache_env_directory_path(temp_dir):
    """Test with DV_FLOW_CACHE pointing to directory"""
    cache_dir = temp_dir / "cache"
    cache_dir.mkdir()
    
    old_env = os.environ.get('DV_FLOW_CACHE')
    try:
        os.environ['DV_FLOW_CACHE'] = str(cache_dir)
        
        providers = load_cache_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], DirectoryCacheProvider)
        assert providers[0].cache_dir == cache_dir
        assert providers[0].writable
    finally:
        if old_env:
            os.environ['DV_FLOW_CACHE'] = old_env
        else:
            del os.environ['DV_FLOW_CACHE']


def test_cache_env_nonexistent_directory(temp_dir):
    """Test with DV_FLOW_CACHE pointing to non-existent directory"""
    cache_dir = temp_dir / "newcache"
    
    old_env = os.environ.get('DV_FLOW_CACHE')
    try:
        os.environ['DV_FLOW_CACHE'] = str(cache_dir)
        
        providers = load_cache_providers()
        assert len(providers) == 1
        assert cache_dir.exists()  # Should be created
        assert isinstance(providers[0], DirectoryCacheProvider)
    finally:
        if old_env:
            os.environ['DV_FLOW_CACHE'] = old_env
        else:
            del os.environ['DV_FLOW_CACHE']


def test_cache_config_file_yaml(temp_dir):
    """Test loading configuration from YAML file"""
    config_file = temp_dir / "cache_config.yaml"
    cache_dir1 = temp_dir / "cache1"
    cache_dir2 = temp_dir / "cache2"
    cache_dir1.mkdir()
    cache_dir2.mkdir()
    
    config_file.write_text(f"""
caches:
  - type: directory
    path: {cache_dir1}
    writable: true
  - type: directory
    path: {cache_dir2}
    writable: false
""")
    
    providers = load_cache_config_file(config_file)
    assert len(providers) == 2
    
    assert isinstance(providers[0], DirectoryCacheProvider)
    assert providers[0].cache_dir == cache_dir1
    assert providers[0].writable
    
    assert isinstance(providers[1], DirectoryCacheProvider)
    assert providers[1].cache_dir == cache_dir2
    assert not providers[1].writable


def test_cache_config_file_creates_writable_dirs(temp_dir):
    """Test that writable cache directories are created"""
    config_file = temp_dir / "cache_config.yaml"
    cache_dir = temp_dir / "newcache"
    
    config_file.write_text(f"""
caches:
  - type: directory
    path: {cache_dir}
    writable: true
""")
    
    providers = load_cache_config_file(config_file)
    assert len(providers) == 1
    assert cache_dir.exists()


def test_cache_config_empty_file(temp_dir):
    """Test loading empty configuration file"""
    config_file = temp_dir / "cache_config.yaml"
    config_file.write_text("")
    
    providers = load_cache_config_file(config_file)
    assert providers == []


def test_cache_config_no_caches_key(temp_dir):
    """Test configuration file without 'caches' key"""
    config_file = temp_dir / "cache_config.yaml"
    config_file.write_text("other_key: value")
    
    providers = load_cache_config_file(config_file)
    assert providers == []


def test_cache_env_points_to_config_file(temp_dir):
    """Test with DV_FLOW_CACHE pointing to config file"""
    config_file = temp_dir / "cache_config.yaml"
    cache_dir = temp_dir / "cache"
    cache_dir.mkdir()
    
    config_file.write_text(f"""
caches:
  - type: directory
    path: {cache_dir}
    writable: true
""")
    
    old_env = os.environ.get('DV_FLOW_CACHE')
    try:
        os.environ['DV_FLOW_CACHE'] = str(config_file)
        
        providers = load_cache_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], DirectoryCacheProvider)
        assert providers[0].cache_dir == cache_dir
    finally:
        if old_env:
            os.environ['DV_FLOW_CACHE'] = old_env
        else:
            del os.environ['DV_FLOW_CACHE']


def test_cache_config_default_writable(temp_dir):
    """Test that writable defaults to true"""
    config_file = temp_dir / "cache_config.yaml"
    cache_dir = temp_dir / "cache"
    cache_dir.mkdir()
    
    # Config without explicit writable field
    config_file.write_text(f"""
caches:
  - type: directory
    path: {cache_dir}
""")
    
    providers = load_cache_config_file(config_file)
    assert len(providers) == 1
    assert providers[0].writable


def test_cache_env_nonexistent_config_file(temp_dir):
    """Test with DV_FLOW_CACHE pointing to non-existent config file"""
    config_file = temp_dir / "nonexistent.yaml"
    
    old_env = os.environ.get('DV_FLOW_CACHE')
    try:
        os.environ['DV_FLOW_CACHE'] = str(config_file)
        
        providers = load_cache_providers()
        assert providers == []
    finally:
        if old_env:
            os.environ['DV_FLOW_CACHE'] = old_env
        else:
            del os.environ['DV_FLOW_CACHE']
