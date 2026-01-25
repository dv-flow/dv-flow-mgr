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
