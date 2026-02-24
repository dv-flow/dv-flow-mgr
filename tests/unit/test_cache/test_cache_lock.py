"""
Test file locking utility
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from dv_flow.mgr.cache_lock import FileLock


@pytest.fixture
def temp_dir():
    """Create a temporary directory for lock files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_exclusive_lock_acquire_release(temp_dir):
    async def _impl():
        """Test acquiring and releasing an exclusive lock"""
        lock_file = temp_dir / "test.lock"
        
        async with FileLock(lock_file, shared=False, timeout=5) as lock:
            assert lock is not None
            assert lock_file.exists()
        
        # Lock should be released after context exit
    asyncio.run(_impl())

def test_shared_lock_multiple_readers(temp_dir):
    async def _impl():
        """Test that multiple shared locks can be acquired simultaneously"""
        lock_file = temp_dir / "test.lock"
        
        # Acquire first shared lock
        lock1 = FileLock(lock_file, shared=True, timeout=5)
        await lock1.__aenter__()
        
        try:
            # Acquire second shared lock (should succeed)
            lock2 = FileLock(lock_file, shared=True, timeout=5)
            await lock2.__aenter__()
            
            try:
                # Both locks should be held
                assert lock_file.exists()
            finally:
                await lock2.__aexit__(None, None, None)
        finally:
            await lock1.__aexit__(None, None, None)
    asyncio.run(_impl())

def test_exclusive_lock_blocks_other_exclusive(temp_dir):
    async def _impl():
        """Test that exclusive lock blocks another exclusive lock"""
        lock_file = temp_dir / "test.lock"
        
        # Acquire first exclusive lock
        lock1 = FileLock(lock_file, shared=False, timeout=5)
        await lock1.__aenter__()
        
        try:
            # Try to acquire second exclusive lock (should timeout)
            lock2 = FileLock(lock_file, shared=False, timeout=1)
            
            with pytest.raises(TimeoutError) as exc_info:
                await lock2.__aenter__()
            
            assert "Failed to acquire exclusive lock" in str(exc_info.value)
        finally:
            await lock1.__aexit__(None, None, None)
    asyncio.run(_impl())

def test_exclusive_lock_blocks_shared(temp_dir):
    async def _impl():
        """Test that exclusive lock blocks shared lock"""
        lock_file = temp_dir / "test.lock"
        
        # Acquire exclusive lock
        lock1 = FileLock(lock_file, shared=False, timeout=5)
        await lock1.__aenter__()
        
        try:
            # Try to acquire shared lock (should timeout)
            lock2 = FileLock(lock_file, shared=True, timeout=1)
            
            with pytest.raises(TimeoutError) as exc_info:
                await lock2.__aenter__()
            
            assert "Failed to acquire shared lock" in str(exc_info.value)
        finally:
            await lock1.__aexit__(None, None, None)
    asyncio.run(_impl())

def test_shared_lock_blocks_exclusive(temp_dir):
    async def _impl():
        """Test that shared lock blocks exclusive lock"""
        lock_file = temp_dir / "test.lock"
        
        # Acquire shared lock
        lock1 = FileLock(lock_file, shared=True, timeout=5)
        await lock1.__aenter__()
        
        try:
            # Try to acquire exclusive lock (should timeout)
            lock2 = FileLock(lock_file, shared=False, timeout=1)
            
            with pytest.raises(TimeoutError) as exc_info:
                await lock2.__aenter__()
            
            assert "Failed to acquire exclusive lock" in str(exc_info.value)
        finally:
            await lock1.__aexit__(None, None, None)
    asyncio.run(_impl())

def test_lock_creates_parent_directory(temp_dir):
    async def _impl():
        """Test that lock creation creates parent directory"""
        lock_file = temp_dir / "subdir" / "test.lock"
        
        async with FileLock(lock_file, shared=False, timeout=5):
            assert lock_file.parent.exists()
            assert lock_file.exists()
    asyncio.run(_impl())

def test_lock_sequential_acquisition(temp_dir):
    async def _impl():
        """Test that locks can be acquired sequentially"""
        lock_file = temp_dir / "test.lock"
        results = []
        
        # First task
        async def task1():
            async with FileLock(lock_file, shared=False, timeout=5):
                results.append('task1_start')
                await asyncio.sleep(0.2)
                results.append('task1_end')
        
        # Second task
        async def task2():
            await asyncio.sleep(0.1)  # Start after task1
            async with FileLock(lock_file, shared=False, timeout=5):
                results.append('task2_start')
                await asyncio.sleep(0.1)
                results.append('task2_end')
        
        # Run both tasks
        await asyncio.gather(task1(), task2())
        
        # Verify tasks ran sequentially
        assert results == ['task1_start', 'task1_end', 'task2_start', 'task2_end']
    asyncio.run(_impl())

def test_context_manager_exception_handling(temp_dir):
    async def _impl():
        """Test that lock is released even when exception occurs"""
        lock_file = temp_dir / "test.lock"
        
        with pytest.raises(ValueError):
            async with FileLock(lock_file, shared=False, timeout=5):
                raise ValueError("Test exception")
        
        # Lock should be released, so we can acquire it again
        async with FileLock(lock_file, shared=False, timeout=5):
            pass  # Should succeed
    asyncio.run(_impl())
