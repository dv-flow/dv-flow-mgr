"""
Test the default hash provider
"""

import pytest
import tempfile
from pathlib import Path
from dv_flow.mgr.hash_provider_default import DefaultHashProvider
from dv_flow.mgr.fileset import FileSet


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_supports_all_filetypes():
    """Default provider should support all file types"""
    provider = DefaultHashProvider()
    
    assert provider.supports('systemVerilogSource')
    assert provider.supports('cSource')
    assert provider.supports('any_filetype')


@pytest.mark.asyncio
async def test_hash_simple_fileset(temp_dir):
    """Test hashing a simple fileset with one file"""
    # Create test file
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    # Create fileset
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    # Hash should be consistent
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    assert hash1 == hash2
    
    # Hash should be a valid MD5 (32 hex chars)
    assert len(hash1) == 32
    assert all(c in '0123456789abcdef' for c in hash1)


@pytest.mark.asyncio
async def test_hash_changes_with_content(temp_dir):
    """Test that hash changes when file content changes"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    # Change file content
    test_file.write_text("Goodbye, World!")
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_hash_multiple_files(temp_dir):
    """Test hashing a fileset with multiple files"""
    file1 = temp_dir / "file1.txt"
    file2 = temp_dir / "file2.txt"
    file1.write_text("Content 1")
    file2.write_text("Content 2")
    
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['file1.txt', 'file2.txt']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    # Hash should be different from single file
    fileset_single = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['file1.txt']
    )
    hash_single = await provider.compute_hash(fileset_single, str(temp_dir))
    
    assert hash1 != hash_single


@pytest.mark.asyncio
async def test_hash_file_order_independent(temp_dir):
    """Test that file order doesn't affect hash (files are sorted)"""
    file1 = temp_dir / "file1.txt"
    file2 = temp_dir / "file2.txt"
    file1.write_text("Content 1")
    file2.write_text("Content 2")
    
    fileset1 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['file1.txt', 'file2.txt']
    )
    
    fileset2 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['file2.txt', 'file1.txt']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset1, str(temp_dir))
    hash2 = await provider.compute_hash(fileset2, str(temp_dir))
    
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_hash_includes_filetype(temp_dir):
    """Test that different filetypes produce different hashes"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    fileset1 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt']
    )
    
    fileset2 = FileSet(
        filetype='cSource',
        basedir=str(temp_dir),
        files=['test.txt']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset1, str(temp_dir))
    hash2 = await provider.compute_hash(fileset2, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_hash_includes_defines(temp_dir):
    """Test that defines affect the hash"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    fileset1 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt'],
        defines=['DEBUG=1']
    )
    
    fileset2 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt'],
        defines=['DEBUG=0']
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset1, str(temp_dir))
    hash2 = await provider.compute_hash(fileset2, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_hash_includes_params(temp_dir):
    """Test that params affect the hash"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    fileset1 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt'],
        params={'opt': 'value1'}
    )
    
    fileset2 = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['test.txt'],
        params={'opt': 'value2'}
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset1, str(temp_dir))
    hash2 = await provider.compute_hash(fileset2, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_hash_missing_file(temp_dir):
    """Test hashing when a file doesn't exist"""
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=['nonexistent.txt']
    )
    
    provider = DefaultHashProvider()
    # Should not raise, but produce a hash
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert len(hash1) == 32
    
    # Hash should be different if file exists
    test_file = temp_dir / "nonexistent.txt"
    test_file.write_text("Now I exist!")
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_hash_absolute_paths(temp_dir):
    """Test hashing with absolute file paths"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")
    
    fileset = FileSet(
        filetype='text',
        basedir=str(temp_dir),
        files=[str(test_file)]  # Absolute path
    )
    
    provider = DefaultHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert len(hash1) == 32
