"""
Unit tests for AgentToolHttp task.

Tests use mocked aiohttp to validate the task logic without requiring
actual HTTP servers to be running.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import aiohttp

from dv_flow.mgr.std.agent_tool_http import (
    AgentToolHttp,
    AgentToolHttpMemento
)
from dv_flow.mgr import TaskDataResult, SeverityE


class MockParams:
    """Mock parameters object"""
    def __init__(self, url="", validate=False, health_check_path="", headers=None, timeout=5):
        self.url = url
        self.validate = validate
        self.health_check_path = health_check_path
        self.headers = headers or {}
        self.timeout = timeout


class MockInput:
    """Mock task input"""
    def __init__(self, params=None, memento=None):
        self.name = "test_agent_tool_http"
        self.params = params or MockParams()
        self.memento = memento
        self.rundir = "/tmp/test_rundir"
        self.srcdir = "/tmp/test_srcdir"


@pytest.mark.asyncio
async def test_basic_url_validation():
    """Test basic URL format validation without accessibility check"""
    params = MockParams(url="http://localhost:8080")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].type == "std.AgentTool"
    assert result.output[0].url == "http://localhost:8080"
    assert result.output[0].command == ""
    assert result.output[0].args == []
    assert result.changed is True


@pytest.mark.asyncio
async def test_https_url():
    """Test HTTPS URL validation"""
    params = MockParams(url="https://api.example.com/mcp")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    assert result.output[0].url == "https://api.example.com/mcp"


@pytest.mark.asyncio
async def test_missing_url_parameter():
    """Test error when required URL parameter is missing"""
    params = MockParams(url="")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert len(result.markers) >= 1
    assert any("url' is required" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_invalid_url_format_no_scheme():
    """Test error on invalid URL format (missing scheme)"""
    params = MockParams(url="localhost:8080")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert any("Invalid URL format" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_invalid_url_format_no_host():
    """Test error on invalid URL format (missing host)"""
    params = MockParams(url="http://")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert any("Invalid URL format" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_unsupported_url_scheme():
    """Test error on unsupported URL scheme"""
    params = MockParams(url="ftp://example.com")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert any("Unsupported URL scheme" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_url_validation_success():
    """Test successful URL accessibility validation"""
    params = MockParams(url="http://localhost:8080", validate=True)
    input_obj = MockInput(params=params)
    
    # Mock aiohttp response
    mock_response = Mock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    assert result.memento.validation_timestamp is not None


@pytest.mark.asyncio
async def test_url_validation_with_health_check():
    """Test URL validation with health check endpoint"""
    params = MockParams(
        url="http://localhost:8080",
        validate=True,
        health_check_path="/health"
    )
    input_obj = MockInput(params=params)
    
    mock_response = Mock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    # Verify that health check URL was called
    mock_session.get.assert_called_once()
    call_args = mock_session.get.call_args
    assert "/health" in call_args[0][0]


@pytest.mark.asyncio
async def test_url_validation_failure_http_error():
    """Test URL validation failure with HTTP error status"""
    params = MockParams(url="http://localhost:8080", validate=True)
    input_obj = MockInput(params=params)
    
    mock_response = Mock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Internal Server Error")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert any("validation failed" in m.msg.lower() for m in result.markers)


@pytest.mark.asyncio
async def test_url_validation_connection_error():
    """Test URL validation failure due to connection error"""
    params = MockParams(url="http://localhost:8080", validate=True)
    input_obj = MockInput(params=params)
    
    # Use a simpler exception that doesn't require complex initialization
    mock_session = Mock()
    mock_session.get = Mock(side_effect=ConnectionError("Connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    # Generic exception handling will catch it
    assert len(result.markers) > 0


@pytest.mark.asyncio
async def test_url_validation_timeout():
    """Test URL validation failure due to timeout"""
    params = MockParams(url="http://slow-server.com", validate=True, timeout=1)
    input_obj = MockInput(params=params)
    
    mock_session = Mock()
    mock_session.get = Mock(side_effect=asyncio.TimeoutError())
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 1
    assert any("timed out" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_validation_skipped_when_disabled():
    """Test that validation is skipped when validate=false"""
    params = MockParams(url="http://unreachable.example.com", validate=False)
    input_obj = MockInput(params=params)
    
    # Should not make any HTTP requests
    with patch('aiohttp.ClientSession') as mock_session:
        result = await AgentToolHttp(None, input_obj)
    
    mock_session.assert_not_called()
    assert result.status == 0


@pytest.mark.asyncio
async def test_custom_headers():
    """Test that custom headers are passed to validation request"""
    params = MockParams(
        url="http://api.example.com",
        validate=True,
        headers={"Authorization": "Bearer token123", "X-Custom": "value"}
    )
    input_obj = MockInput(params=params)
    
    mock_response = Mock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    # Verify headers were passed
    call_kwargs = mock_session.get.call_args[1]
    assert "headers" in call_kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer token123"


@pytest.mark.asyncio
async def test_memento_tracking():
    """Test memento creation and hash tracking"""
    import hashlib
    
    url = "http://localhost:8080"
    params = MockParams(url=url)
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.memento is not None
    assert result.memento.url_hash is not None
    
    # Verify hash matches expected
    expected_hash = hashlib.sha256(url.encode()).hexdigest()
    assert result.memento.url_hash == expected_hash


@pytest.mark.asyncio
async def test_changed_detection():
    """Test that changed flag is set correctly"""
    import hashlib
    
    # First run - no memento
    url = "http://localhost:8080"
    params = MockParams(url=url)
    input_obj = MockInput(params=params)
    
    result1 = await AgentToolHttp(None, input_obj)
    assert result1.changed is True
    
    # Second run - same URL with memento
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    memento = {
        "url_hash": url_hash,
        "validation_timestamp": None
    }
    input_obj2 = MockInput(params=params, memento=memento)
    
    result2 = await AgentToolHttp(None, input_obj2)
    assert result2.changed is False
    
    # Third run - different URL
    params3 = MockParams(url="http://different.example.com")
    input_obj3 = MockInput(params=params3, memento=memento)
    
    result3 = await AgentToolHttp(None, input_obj3)
    assert result3.changed is True


@pytest.mark.asyncio
async def test_custom_timeout():
    """Test custom timeout parameter"""
    params = MockParams(url="http://localhost:8080", validate=True, timeout=10)
    input_obj = MockInput(params=params)
    
    mock_response = Mock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    with patch('aiohttp.ClientSession', return_value=mock_session) as mock_session_cls:
        result = await AgentToolHttp(None, input_obj)
    
    # Verify timeout was set
    mock_session_cls.assert_called_once()
    call_kwargs = mock_session_cls.call_args[1]
    assert "timeout" in call_kwargs
    # ClientTimeout object has total attribute
    assert call_kwargs["timeout"].total == 10


@pytest.mark.asyncio
async def test_invalid_memento_handling():
    """Test graceful handling of invalid memento data"""
    params = MockParams(url="http://localhost:8080")
    input_obj = MockInput(params=params, memento={"invalid": "data"})
    
    result = await AgentToolHttp(None, input_obj)
    
    # Should still succeed despite invalid memento
    assert result.status == 0
    assert result.changed is True


@pytest.mark.asyncio
async def test_url_with_path_and_query():
    """Test URL with path and query parameters"""
    params = MockParams(url="https://api.example.com/v1/mcp?key=value")
    input_obj = MockInput(params=params)
    
    result = await AgentToolHttp(None, input_obj)
    
    assert result.status == 0
    assert result.output[0].url == "https://api.example.com/v1/mcp?key=value"
