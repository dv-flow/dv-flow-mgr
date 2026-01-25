"""
Test cache init command
"""

import pytest
import tempfile
import yaml
from pathlib import Path


def test_cache_init_command():
    """Test cache init command creates directory and config"""
    from dv_flow.mgr.cmds.cache.cmd_init import CmdCacheInit
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "test_cache"
        
        # Create args object
        class Args:
            pass
        
        args = Args()
        args.cache_dir = str(cache_dir)
        args.shared = False
        
        # Run init command
        cmd = CmdCacheInit()
        result = cmd(args)
        
        assert result == 0
        assert cache_dir.exists()
        
        # Check config file
        config_file = cache_dir / '.cache_config.yaml'
        assert config_file.exists()
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert config['type'] == 'directory'
        assert config['version'] == 1
        assert config['shared'] == False
        assert 'created' in config


def test_cache_init_shared():
    """Test cache init with shared flag"""
    from dv_flow.mgr.cmds.cache.cmd_init import CmdCacheInit
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "shared_cache"
        
        class Args:
            pass
        
        args = Args()
        args.cache_dir = str(cache_dir)
        args.shared = True
        
        cmd = CmdCacheInit()
        result = cmd(args)
        
        assert result == 0
        assert cache_dir.exists()
        
        # Check config shows shared=true
        config_file = cache_dir / '.cache_config.yaml'
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert config['shared'] == True


def test_cache_init_existing_directory():
    """Test cache init on existing directory"""
    from dv_flow.mgr.cmds.cache.cmd_init import CmdCacheInit
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "existing"
        cache_dir.mkdir()
        
        # Put a file in it
        (cache_dir / "existing_file.txt").write_text("test")
        
        class Args:
            pass
        
        args = Args()
        args.cache_dir = str(cache_dir)
        args.shared = False
        
        cmd = CmdCacheInit()
        result = cmd(args)
        
        assert result == 0
        # Existing file should still be there
        assert (cache_dir / "existing_file.txt").exists()
        # Config should be created
        assert (cache_dir / '.cache_config.yaml').exists()


def test_cache_init_nested_directory():
    """Test cache init creates parent directories"""
    from dv_flow.mgr.cmds.cache.cmd_init import CmdCacheInit
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "parent" / "child" / "cache"
        
        class Args:
            pass
        
        args = Args()
        args.cache_dir = str(cache_dir)
        args.shared = False
        
        cmd = CmdCacheInit()
        result = cmd(args)
        
        assert result == 0
        assert cache_dir.exists()
        assert (cache_dir / '.cache_config.yaml').exists()
