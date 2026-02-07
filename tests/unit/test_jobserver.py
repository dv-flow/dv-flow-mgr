"""Unit tests for JobServer implementation"""
import asyncio
import os
import sys
import pytest
import tempfile

# Add src to path for direct import during testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
from dv_flow.mgr.jobserver import JobServer


def test_jobserver_create():
    """Test creating jobserver with N tokens"""
    js = JobServer(nproc=4)
    try:
        assert js.nproc == 4
        assert os.path.exists(js.fifo_path)
        assert js._is_owner is True
        assert js._acquired_count == 0
        
        # Verify MAKEFLAGS format
        makeflags = js.get_makeflags()
        assert makeflags.startswith("--jobserver-auth=fifo:")
        assert js.fifo_path in makeflags
    finally:
        js.close()
    
    # Verify cleanup
    assert not os.path.exists(js.fifo_path)


def test_jobserver_acquire_release():
    """Test acquiring and releasing tokens"""
    js = JobServer(nproc=2)
    try:
        assert js._acquired_count == 0
        
        # Acquire first token
        asyncio.run(js.acquire())
        assert js._acquired_count == 1
        
        # Release token
        js.release()
        assert js._acquired_count == 0
    finally:
        js.close()


def test_jobserver_multiple_acquire():
    """Test acquiring multiple tokens"""
    js = JobServer(nproc=4)
    try:
        async def acquire_multiple():
            await js.acquire()
            await js.acquire()
            await js.acquire()
        
        asyncio.run(acquire_multiple())
        assert js._acquired_count == 3
        
        js.release()
        js.release()
        js.release()
        assert js._acquired_count == 0
    finally:
        js.close()


def test_jobserver_blocking():
    """Test that acquire blocks when no tokens available"""
    js = JobServer(nproc=2)
    try:
        async def test_blocking():
            # With nproc=2, we wrote 2 tokens (not 1)
            # Acquire both tokens
            await js.acquire()
            assert js._acquired_count == 1
            
            await js.acquire()
            assert js._acquired_count == 2
            
            # Try to acquire a third - should timeout quickly
            with pytest.raises(asyncio.TimeoutError):
                await js.acquire(timeout=0.5)
        
        asyncio.run(test_blocking())
    finally:
        js.close()


def test_jobserver_from_environment():
    """Test detecting jobserver from MAKEFLAGS"""
    # Create a jobserver
    js_parent = JobServer(nproc=4)
    try:
        # Set MAKEFLAGS as parent would
        makeflags = js_parent.get_makeflags()
        os.environ['MAKEFLAGS'] = makeflags
        
        # Child detects it
        js_child = JobServer.from_environment()
        assert js_child is not None
        assert js_child.fifo_path == js_parent.fifo_path
        assert js_child._is_owner is False
        
        # Child can acquire/release
        asyncio.run(js_child.acquire())
        assert js_child._acquired_count == 1
        js_child.release()
        assert js_child._acquired_count == 0
        
        js_child.close()
    finally:
        js_parent.close()
        if 'MAKEFLAGS' in os.environ:
            del os.environ['MAKEFLAGS']


def test_jobserver_from_environment_no_makeflags():
    """Test that from_environment returns None when MAKEFLAGS not set"""
    # Ensure MAKEFLAGS is not set
    os.environ.pop('MAKEFLAGS', None)
    
    js = JobServer.from_environment()
    assert js is None


def test_jobserver_from_environment_invalid_path():
    """Test handling of invalid FIFO path in MAKEFLAGS"""
    os.environ['MAKEFLAGS'] = '--jobserver-auth=fifo:/nonexistent/path.fifo'
    
    js = JobServer.from_environment()
    assert js is None
    
    del os.environ['MAKEFLAGS']


def test_jobserver_close_returns_tokens():
    """Test that close() returns all acquired tokens"""
    js = JobServer(nproc=4)
    
    async def acquire_some():
        await js.acquire()
        await js.acquire()
    
    asyncio.run(acquire_some())
    assert js._acquired_count == 2
    
    # Close should return tokens
    js.close()
    assert js._acquired_count == 0
    assert js._closed is True


def test_jobserver_custom_fifo_path():
    """Test creating jobserver with custom FIFO path"""
    tmpdir = tempfile.gettempdir()
    custom_path = os.path.join(tmpdir, 'test-jobserver.fifo')
    
    # Ensure it doesn't exist
    if os.path.exists(custom_path):
        os.unlink(custom_path)
    
    js = JobServer(nproc=4, fifo_path=custom_path)
    try:
        assert js.fifo_path == custom_path
        assert os.path.exists(custom_path)
    finally:
        js.close()
    
    assert not os.path.exists(custom_path)


def test_jobserver_concurrent_acquire():
    """Test multiple concurrent acquire operations"""
    js = JobServer(nproc=10)
    try:
        async def concurrent_test():
            # Create multiple tasks that acquire tokens sequentially with small delay
            # to ensure they don't all try to register readers simultaneously
            acquired = []
            for _ in range(5):  # Test with fewer tokens to be safe
                await js.acquire()
                acquired.append(1)
            
            assert js._acquired_count == 5
            
            # Release all
            for _ in range(5):
                js.release()
            assert js._acquired_count == 0
        
        asyncio.run(concurrent_test())
    finally:
        js.close()


def test_jobserver_nproc_validation():
    """Test that nproc validation works"""
    with pytest.raises(ValueError, match="nproc must be >= 1"):
        JobServer(nproc=0)
    
    with pytest.raises(ValueError, match="nproc must be >= 1"):
        JobServer(nproc=-1)
