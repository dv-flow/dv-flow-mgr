"""
Test SystemVerilog hash provider
"""

import pytest
import tempfile
from pathlib import Path
from dv_flow.mgr.hash_provider_sv import SVHashProvider
from dv_flow.mgr.fileset import FileSet


@pytest.fixture
def temp_dir():
    """Create a temporary directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_sv_provider_supports():
    """Test that SV provider supports correct filetypes"""
    provider = SVHashProvider()
    
    assert provider.supports('systemVerilogSource')
    assert provider.supports('verilogSource')
    assert provider.supports('systemVerilogInclude')
    assert provider.supports('verilogInclude')
    assert not provider.supports('cSource')
    assert not provider.supports('text')


@pytest.mark.asyncio
async def test_sv_hash_simple(temp_dir):
    """Test SV hash computation for simple file"""
    # Create SV file
    sv_file = temp_dir / "test.sv"
    sv_file.write_text("module test; endmodule\n")
    
    fileset = FileSet(
        filetype='systemVerilogSource',
        basedir=str(temp_dir),
        files=['test.sv']
    )
    
    provider = SVHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash1 is not None
    assert len(hash1) == 32
    
    # Deterministic
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_sv_hash_with_includes(temp_dir):
    """Test SV hash includes dependency files"""
    # Create include file
    inc_file = temp_dir / "defs.svh"
    inc_file.write_text("`define WIDTH 32\n")
    
    # Create main file
    main_file = temp_dir / "main.sv"
    main_file.write_text('`include "defs.svh"\nmodule main; endmodule\n')
    
    fileset = FileSet(
        filetype='systemVerilogSource',
        basedir=str(temp_dir),
        files=['main.sv'],
        incdirs=[str(temp_dir)]
    )
    
    provider = SVHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    # Change include - hash should change
    inc_file.write_text("`define WIDTH 64\n")
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_sv_hash_nested_includes(temp_dir):
    """Test SV hash handles nested includes"""
    # Create nested includes
    inc1 = temp_dir / "inc1.svh"
    inc1.write_text("`define LEVEL1 1\n")
    
    inc2 = temp_dir / "inc2.svh"
    inc2.write_text('`include "inc1.svh"\n`define LEVEL2 2\n')
    
    main = temp_dir / "main.sv"
    main.write_text('`include "inc2.svh"\nmodule main; endmodule\n')
    
    fileset = FileSet(
        filetype='systemVerilogSource',
        basedir=str(temp_dir),
        files=['main.sv'],
        incdirs=[str(temp_dir)]
    )
    
    provider = SVHashProvider()
    hash1 = await provider.compute_hash(fileset, str(temp_dir))
    
    # Change deeply nested include
    inc1.write_text("`define LEVEL1 10\n")
    hash2 = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_sv_hash_fallback_when_svdep_unavailable(temp_dir, monkeypatch):
    """Test that provider falls back to default when svdep not available"""
    # Mock svdep as unavailable
    import sys
    monkeypatch.setitem(sys.modules, 'svdep', None)
    monkeypatch.setitem(sys.modules, 'svdep.native', None)
    
    sv_file = temp_dir / "test.sv"
    sv_file.write_text("module test; endmodule\n")
    
    fileset = FileSet(
        filetype='systemVerilogSource',
        basedir=str(temp_dir),
        files=['test.sv']
    )
    
    provider = SVHashProvider()
    # Should fall back to default hash
    hash_value = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash_value is not None
    assert len(hash_value) == 32


@pytest.mark.asyncio
async def test_sv_hash_multiple_files(temp_dir):
    """Test SV hash for multiple root files"""
    file1 = temp_dir / "file1.sv"
    file1.write_text("module file1; endmodule\n")
    
    file2 = temp_dir / "file2.sv"  
    file2.write_text("module file2; endmodule\n")
    
    fileset = FileSet(
        filetype='systemVerilogSource',
        basedir=str(temp_dir),
        files=['file1.sv', 'file2.sv']
    )
    
    provider = SVHashProvider()
    hash_value = await provider.compute_hash(fileset, str(temp_dir))
    
    assert hash_value is not None
    assert len(hash_value) == 32
