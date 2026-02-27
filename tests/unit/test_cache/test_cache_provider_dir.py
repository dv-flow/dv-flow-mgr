import asyncio
"""
Test directory cache provider
"""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from dv_flow.mgr.cache_provider_dir import DirectoryCacheProvider
from dv_flow.mgr.cache_provider import CacheEntry, CompressionType


@pytest.fixture
def temp_dir():
    """Create a temporary directory for cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_cache_provider_init(temp_dir):
    async def _impl():
        """Test cache provider initialization"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        assert provider.cache_dir == cache_dir
        assert provider.writable
        assert cache_dir.exists()
    asyncio.run(_impl())

def test_cache_entry_not_exists(temp_dir):
    async def _impl():
        """Test checking for non-existent entry"""
        provider = DirectoryCacheProvider(temp_dir, writable=True)
        
        exists = await provider.exists("task1:abc123")
        assert not exists
        
        entry = await provider.get("task1:abc123")
        assert entry is None
    asyncio.run(_impl())

def test_put_and_get_entry(temp_dir):
    async def _impl():
        """Test storing and retrieving cache entry"""
        provider = DirectoryCacheProvider(temp_dir, writable=True)
        
        # Create entry
        entry = CacheEntry(
            key="task1:abc123",
            output_template={"result": "success", "files": ["${{ rundir }}/output.txt"]},
            artifacts_path=None,
            compression=CompressionType.No,
            created=datetime.now(),
            metadata={"user": "test", "machine": "localhost"}
        )
        
        # Store entry
        success = await provider.put("task1:abc123", entry)
        assert success
        
        # Check existence
        exists = await provider.exists("task1:abc123")
        assert exists
        
        # Retrieve entry
        retrieved = await provider.get("task1:abc123")
        assert retrieved is not None
        assert retrieved.key == "task1:abc123"
        assert retrieved.output_template == entry.output_template
        assert retrieved.metadata == entry.metadata
    asyncio.run(_impl())

def test_entry_directory_structure(temp_dir):
    async def _impl():
        """Test that cache entries have correct directory structure"""
        provider = DirectoryCacheProvider(temp_dir, writable=True)
        
        entry = CacheEntry(
            key="mytask:hash123",
            output_template={"result": "ok"},
            metadata={}
        )
        
        await provider.put("mytask:hash123", entry)
        
        # Check directory structure
        entry_dir = temp_dir / "mytask" / "hash123"
        assert entry_dir.exists()
        assert (entry_dir / "output.json").exists()
        assert (entry_dir / "metadata.json").exists()
        assert (entry_dir / ".lock").exists()
    asyncio.run(_impl())

def test_invalid_key_format(temp_dir):
    async def _impl():
        """Test that invalid key format raises error"""
        provider = DirectoryCacheProvider(temp_dir, writable=True)
        
        with pytest.raises(ValueError) as exc_info:
            await provider.exists("invalid_key_without_colon")
        
        assert "Invalid cache key format" in str(exc_info.value)
    asyncio.run(_impl())

def test_readonly_provider_cannot_write(temp_dir):
    async def _impl():
        """Test that readonly provider cannot write"""
        provider = DirectoryCacheProvider(temp_dir, writable=False)
        
        entry = CacheEntry(
            key="task1:abc123",
            output_template={"result": "success"},
            metadata={}
        )
        
        success = await provider.put("task1:abc123", entry)
        assert not success
    asyncio.run(_impl())

def test_store_and_extract_artifacts_uncompressed(temp_dir):
    async def _impl():
        """Test storing and extracting uncompressed artifacts"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        # Create artifacts directory
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "file1.txt").write_text("Content 1")
        (artifacts_dir / "file2.txt").write_text("Content 2")
        (artifacts_dir / "subdir").mkdir()
        (artifacts_dir / "subdir" / "file3.txt").write_text("Content 3")
        
        # Store artifacts
        key = "task1:abc123"
        success = await provider.store_artifacts(key, artifacts_dir, CompressionType.No)
        assert success
        
        # Create cache entry
        entry = CacheEntry(
            key=key,
            output_template={"result": "ok"},
            artifacts_path="artifacts",
            compression=CompressionType.No,
            metadata={}
        )
        await provider.put(key, entry)
        
        # Extract artifacts to new location
        extract_dir = temp_dir / "extracted"
        retrieved = await provider.get(key)
        success = await provider.extract_artifacts(retrieved, extract_dir, use_symlinks=False)
        assert success
        
        # Verify extracted files
        assert (extract_dir / "file1.txt").read_text() == "Content 1"
        assert (extract_dir / "file2.txt").read_text() == "Content 2"
        assert (extract_dir / "subdir" / "file3.txt").read_text() == "Content 3"
    asyncio.run(_impl())

def test_store_and_extract_artifacts_gzip(temp_dir):
    async def _impl():
        """Test storing and extracting gzip compressed artifacts"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        # Create artifacts directory
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "file1.txt").write_text("Content 1")
        (artifacts_dir / "file2.txt").write_text("Content 2")
        
        # Store artifacts with compression
        key = "task1:abc123"
        success = await provider.store_artifacts(key, artifacts_dir, CompressionType.Gzip)
        assert success
        
        # Verify compressed archive exists
        entry_dir = cache_dir / "task1" / "abc123"
        assert (entry_dir / "artifacts.tar.gz").exists()
        
        # Create cache entry
        entry = CacheEntry(
            key=key,
            output_template={"result": "ok"},
            artifacts_path="artifacts.tar.gz",
            compression=CompressionType.Gzip,
            metadata={}
        )
        await provider.put(key, entry)
        
        # Extract artifacts
        extract_dir = temp_dir / "extracted"
        retrieved = await provider.get(key)
        success = await provider.extract_artifacts(retrieved, extract_dir, use_symlinks=False)
        assert success
        
        # Verify extracted files
        assert (extract_dir / "artifacts" / "file1.txt").read_text() == "Content 1"
        assert (extract_dir / "artifacts" / "file2.txt").read_text() == "Content 2"
    asyncio.run(_impl())

def test_extract_with_symlinks(temp_dir):
    async def _impl():
        """Test extracting artifacts using symlinks"""
        cache_dir = temp_dir / "cache"
        provider = DirectoryCacheProvider(cache_dir, writable=True)
        
        # Create and store artifacts
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "file1.txt").write_text("Content 1")
        
        key = "task1:abc123"
        await provider.store_artifacts(key, artifacts_dir, CompressionType.No)
        
        entry = CacheEntry(
            key=key,
            output_template={"result": "ok"},
            artifacts_path="artifacts",
            compression=CompressionType.No,
            metadata={}
        )
        await provider.put(key, entry)
        
        # Extract with symlinks
        extract_dir = temp_dir / "extracted"
        retrieved = await provider.get(key)
        success = await provider.extract_artifacts(retrieved, extract_dir, use_symlinks=True)
        assert success
        
        # Verify symlink was created
        extracted_file = extract_dir / "file1.txt"
        assert extracted_file.is_symlink()
        assert extracted_file.read_text() == "Content 1"
    asyncio.run(_impl())

def test_entry_with_no_artifacts(temp_dir):
    async def _impl():
        """Test cache entry without artifacts"""
        provider = DirectoryCacheProvider(temp_dir, writable=True)
        
        # Entry without artifacts
        entry = CacheEntry(
            key="task1:abc123",
            output_template={"result": "success", "value": 42},
            artifacts_path=None,
            compression=CompressionType.No,
            metadata={}
        )
        
        await provider.put("task1:abc123", entry)
        
        # Retrieve and extract (should succeed with no artifacts)
        retrieved = await provider.get("task1:abc123")
        extract_dir = temp_dir / "extracted"
        success = await provider.extract_artifacts(retrieved, extract_dir)
        assert success
    asyncio.run(_impl())
