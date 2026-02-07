"""
Simple integration test to verify AgentToolStdio and AgentToolHttp work in practice.

Run with: pytest tests/integration/test_simple_agent_tools.py -v -s
"""
import pytest
import tempfile
import asyncio
from pathlib import Path


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_tool_stdio_basic():
    """Test AgentToolStdio with echo command"""
    from dv_flow.mgr.std.agent_tool_stdio import AgentToolStdio
    
    class MockParams:
        command = "echo"
        args = ["test"]
        install_command = ""
        env = {}
    
    class MockInput:
        name = "test_echo"
        params = MockParams()
        memento = None
        rundir = tempfile.gettempdir()
        srcdir = tempfile.gettempdir()
    
    result = await AgentToolStdio(None, MockInput())
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].command == "echo"
    assert result.output[0].args == ["test"]
    print(f"✓ AgentToolStdio successfully configured: {result.output[0].command}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_tool_http_no_validation():
    """Test AgentToolHttp without validation"""
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    
    class MockParams:
        url = "http://localhost:8080/mcp"
        validate = False
        health_check_path = ""
        headers = {}
        timeout = 5
    
    class MockInput:
        name = "test_http"
        params = MockParams()
        memento = None
        rundir = tempfile.gettempdir()
        srcdir = tempfile.gettempdir()
    
    result = await AgentToolHttp(None, MockInput())
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].url == "http://localhost:8080/mcp"
    print(f"✓ AgentToolHttp successfully configured: {result.output[0].url}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_tool_http_with_real_validation():
    """Test AgentToolHttp with validation against a real endpoint"""
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    
    class MockParams:
        url = "https://httpbin.org"
        validate = True
        health_check_path = "/status/200"
        headers = {}
        timeout = 10
    
    class MockInput:
        name = "test_httpbin"
        params = MockParams()
        memento = None
        rundir = tempfile.gettempdir()
        srcdir = tempfile.gettempdir()
    
    result = await AgentToolHttp(None, MockInput())
    
    assert result.status == 0
    assert result.memento.validation_timestamp is not None
    print(f"✓ AgentToolHttp validated successfully: {result.output[0].url}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
