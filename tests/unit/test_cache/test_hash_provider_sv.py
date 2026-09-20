import asyncio
"""
Test SystemVerilog hash provider
"""

import pytest
import tempfile
from pathlib import Path
from dv_flow.mgr.hash_provider_sv import SVHashProvider
from dv_flow.mgr.fileset import FileSet
from dv_flow.mgr.hash_provider import collect_incdirs, compute_hash


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


def test_sv_hash_simple(temp_dir):
    async def _impl():
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
    asyncio.run(_impl())

def test_sv_hash_with_includes(temp_dir):
    pytest.importorskip('svdep', reason="svdep module required for include tracking")
    async def _impl():
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
    asyncio.run(_impl())

def test_sv_hash_nested_includes(temp_dir):
    pytest.importorskip('svdep', reason="svdep module required for include tracking")
    async def _impl():
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
    asyncio.run(_impl())

def test_sv_hash_fallback_when_svdep_unavailable(temp_dir, monkeypatch):
    async def _impl():
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
    asyncio.run(_impl())

def test_sv_hash_multiple_files(temp_dir):
    async def _impl():
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
    asyncio.run(_impl())


def test_sv_hash_relative_incdir_resolves_against_basedir(temp_dir):
    pytest.importorskip('svdep', reason="svdep module required for include tracking")
    async def _impl():
        """A relative incdir names a dir under basedir, not under rundir.

        `FileSet(basedir=$UVM_HOME, incdirs=["src"])` is the shape SimLibUVM
        emits; resolved against the rundir it names nothing and the include
        drops out of the hash.
        """
        (temp_dir / "inc").mkdir()
        inc_file = temp_dir / "inc" / "defs.svh"
        inc_file.write_text("`define WIDTH 32\n")

        (temp_dir / "src").mkdir()
        main_file = temp_dir / "src" / "main.sv"
        main_file.write_text('`include "defs.svh"\nmodule main; endmodule\n')

        fileset = FileSet(
            filetype='systemVerilogSource',
            basedir=str(temp_dir),
            files=['src/main.sv'],
            incdirs=['inc'])

        provider = SVHashProvider()
        # rundir deliberately != basedir: only basedir-relative resolution works
        rundir = str(temp_dir / "run")
        hash1 = await provider.compute_hash(fileset, rundir)

        inc_file.write_text("`define WIDTH 64\n")
        hash2 = await provider.compute_hash(fileset, rundir)

        assert hash1 != hash2
    asyncio.run(_impl())


def test_sv_hash_cross_fileset_include(temp_dir):
    pytest.importorskip('svdep', reason="svdep module required for include tracking")
    async def _impl():
        """An include satisfied by a SIBLING fileset's incdir must be hashed.

        This is the UVM case: the env package `include`s uvm_macros.svh, which
        only the UVM library fileset's incdir can resolve. Hashing the env
        fileset alone misses it, so edits to the macro file would not force a
        rebuild.
        """
        (temp_dir / "lib").mkdir()
        macros = temp_dir / "lib" / "macros.svh"
        macros.write_text("`define M 1\n")

        (temp_dir / "env").mkdir()
        env_pkg = temp_dir / "env" / "env_pkg.sv"
        env_pkg.write_text('`include "macros.svh"\npackage env_pkg; endpackage\n')

        lib_fs = FileSet(
            filetype='systemVerilogSource',
            basedir=str(temp_dir / "lib"),
            files=[],
            incdirs=['.'])
        env_fs = FileSet(
            filetype='systemVerilogSource',
            basedir=str(temp_dir / "env"),
            files=['env_pkg.sv'])

        incdirs = collect_incdirs([lib_fs, env_fs], str(temp_dir))
        assert str((temp_dir / "lib").resolve()) in incdirs

        provider = SVHashProvider()
        hash1 = await provider.compute_hash(env_fs, str(temp_dir), incdirs=incdirs)

        macros.write_text("`define M 2\n")
        hash2 = await provider.compute_hash(env_fs, str(temp_dir), incdirs=incdirs)

        assert hash1 != hash2, "sibling-fileset include not covered by the hash"

        # ... and without the sibling incdirs the include is invisible
        blind1 = await provider.compute_hash(env_fs, str(temp_dir))
        macros.write_text("`define M 3\n")
        blind2 = await provider.compute_hash(env_fs, str(temp_dir))
        assert blind1 == blind2
    asyncio.run(_impl())


def test_compute_hash_helper_tolerates_legacy_provider(temp_dir):
    async def _impl():
        """A provider predating `incdirs` is still callable."""
        class LegacyProvider:
            def supports(self, filetype):
                return True

            async def compute_hash(self, fileset, rundir):
                return "0" * 32

        fileset = FileSet(
            filetype='systemVerilogSource',
            basedir=str(temp_dir),
            files=[])
        assert await compute_hash(
            LegacyProvider(), fileset, str(temp_dir), ["/nonexistent"]) == "0" * 32
    asyncio.run(_impl())
