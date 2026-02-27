import asyncio
"""
Test the hash provider registry in ExtRgy
"""

import pytest
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.hash_provider_default import DefaultHashProvider
from dv_flow.mgr.fileset import FileSet


class MockHashProvider:
    """Mock hash provider for testing"""
    
    def __init__(self, supported_types, hash_value="mock_hash"):
        self.supported_types = supported_types
        self.hash_value = hash_value
    
    def supports(self, filetype: str) -> bool:
        return filetype in self.supported_types
    
    async def compute_hash(self, fileset: FileSet, rundir: str) -> str:
        return self.hash_value


def test_default_provider_registered():
    """Test that appropriate providers are registered automatically"""
    registry = ExtRgy.inst()
    
    # Should find SV provider for SystemVerilog (higher priority)
    sv_provider = registry.get_hash_provider('systemVerilogSource')
    assert sv_provider is not None
    from dv_flow.mgr.hash_provider_sv import SVHashProvider
    assert isinstance(sv_provider, SVHashProvider)
    
    # Should find default provider for non-SV types
    text_provider = registry.get_hash_provider('text')
    assert text_provider is not None
    assert isinstance(text_provider, DefaultHashProvider)


def test_register_custom_provider():
    """Test registering a custom hash provider"""
    registry = ExtRgy()
    registry._discover_plugins()
    
    # Register a custom provider for a non-SV type with high priority
    custom_provider = MockHashProvider(['cSource'], 'custom_hash')
    registry.register_hash_provider(custom_provider, priority=20)
    
    # Should get custom provider for cSource (higher priority than default)
    provider = registry.get_hash_provider('cSource')
    assert provider is custom_provider
    
    # Should still get default provider for types not matching custom
    text_provider = registry.get_hash_provider('text')
    assert isinstance(text_provider, DefaultHashProvider)


def test_provider_priority():
    """Test that higher priority providers are returned first"""
    registry = ExtRgy()
    registry._discover_plugins()
    
    # Register multiple providers with different priorities
    low_priority = MockHashProvider(['text'], 'low')
    mid_priority = MockHashProvider(['text'], 'mid')
    high_priority = MockHashProvider(['text'], 'high')
    
    registry.register_hash_provider(low_priority, priority=1)
    registry.register_hash_provider(high_priority, priority=10)
    registry.register_hash_provider(mid_priority, priority=5)
    
    # Should get highest priority provider
    provider = registry.get_hash_provider('text')
    assert provider is high_priority


def test_provider_fallback():
    """Test that providers fall back if not supported"""
    registry = ExtRgy()
    registry._discover_plugins()
    
    # Register provider that only supports specific type with very high priority
    specific_provider = MockHashProvider(['customType'], 'specific')
    registry.register_hash_provider(specific_provider, priority=100)
    
    # Should get specific provider for supported type
    provider = registry.get_hash_provider('customType')
    assert provider is specific_provider
    
    # Should fall back to default for unsupported type
    provider = registry.get_hash_provider('cSource')
    assert isinstance(provider, DefaultHashProvider)


def test_no_provider_found():
    """Test behavior when no provider supports a filetype"""
    registry = ExtRgy()
    # Don't call _discover_plugins, so no providers registered
    
    provider = registry.get_hash_provider('anytype')
    assert provider is None


def test_copy_preserves_providers():
    """Test that copying registry preserves hash providers"""
    registry = ExtRgy()
    registry._discover_plugins()
    
    custom_provider = MockHashProvider(['text'], 'custom')
    registry.register_hash_provider(custom_provider, priority=10)
    
    # Copy registry
    copy = registry.copy()
    
    # Should have the same providers
    provider = copy.get_hash_provider('text')
    assert provider is custom_provider
    
    provider = copy.get_hash_provider('cSource')
    assert isinstance(provider, DefaultHashProvider)


def test_provider_integration():
    async def _impl():
        """Integration test using actual hash computation"""
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            test_file = tmpdir / "test.txt"
            test_file.write_text("Test content")
            
            fileset = FileSet(
                filetype='text',
                basedir=str(tmpdir),
                files=['test.txt']
            )
            
            registry = ExtRgy.inst()
            provider = registry.get_hash_provider('text')
            
            assert provider is not None
            hash_value = await provider.compute_hash(fileset, str(tmpdir))
            
            # Should be a valid MD5 hash
            assert len(hash_value) == 32
            assert all(c in '0123456789abcdef' for c in hash_value)
    asyncio.run(_impl())
