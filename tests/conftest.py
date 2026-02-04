"""
Global pytest configuration for dv-flow tests.
Ensures cache is disabled by default for all tests except cache-specific tests.
"""
import os
import pytest


@pytest.fixture(autouse=True)
def disable_cache_by_default(request):
    """
    Disable cache by default for all tests.
    Cache tests can override by setting DV_FLOW_CACHE explicitly.
    """
    # Check if test is in cache test directory
    test_file = str(request.fspath)
    is_cache_test = 'test_cache' in test_file
    
    # Save original env
    original_cache = os.environ.get('DV_FLOW_CACHE')
    
    # Only unset if not a cache test
    if not is_cache_test and original_cache is not None:
        del os.environ['DV_FLOW_CACHE']
    
    yield
    
    # Restore original env
    if original_cache is not None and not is_cache_test:
        os.environ['DV_FLOW_CACHE'] = original_cache
    elif original_cache is None and 'DV_FLOW_CACHE' in os.environ and not is_cache_test:
        del os.environ['DV_FLOW_CACHE']


# Lazy import to avoid import issues in test collection
def _get_assistant_registry():
    from dv_flow.mgr.std.ai_assistant import ASSISTANT_REGISTRY
    return ASSISTANT_REGISTRY

def _get_assistant_priority():
    from dv_flow.mgr.std.ai_assistant import ASSISTANT_PRIORITY
    return ASSISTANT_PRIORITY


@pytest.fixture(params=["copilot", "codex"])
def assistant_name(request):
    """Parameterized fixture that yields each assistant name in priority order.
    
    Use this to test functionality across all supported assistants.
    Tests using this fixture will run once for each assistant in ASSISTANT_PRIORITY.
    
    Example:
        def test_something(assistant_name):
            assert assistant_name in ['copilot', 'codex']
    """
    return request.param


@pytest.fixture
def available_assistant(assistant_name):
    """Fixture that skips test if the specified assistant is not available.
    
    Use this when you need to test actual assistant functionality
    that requires the CLI to be installed.
    
    Example:
        def test_real_execution(available_assistant):
            name, assistant = available_assistant
            # This only runs if the assistant is actually available
    """
    if assistant_name not in _get_assistant_registry():
        pytest.skip(f"Assistant '{assistant_name}' not in registry")
    
    assistant = _get_assistant_registry()[assistant_name]()
    is_available, error_msg = assistant.check_available()
    
    if not is_available:
        pytest.skip(f"{assistant_name} not available: {error_msg}")
    
    return assistant_name, assistant


@pytest.fixture(params=["mock", "copilot", "codex", "openai", "claude"])
def all_assistant_names(request):
    """Fixture that yields ALL registered assistant names (not just priority ones).
    
    Use this when testing registry functionality.
    """
    return request.param
