"""
Unit tests for AgentToolStdio task.

Tests use mocked subprocess and file system operations to validate
the task logic without requiring actual MCP servers to be installed.
"""
import pytest
import os
import asyncio
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from dv_flow.mgr.std.agent_tool_stdio import (
    AgentToolStdio,
    AgentToolStdioMemento
)
from dv_flow.mgr import TaskDataResult, SeverityE


class MockParams:
    """Mock parameters object"""
    def __init__(self, command="", args=None, install_command="", env=None):
        self.command = command
        self.args = args or []
        self.install_command = install_command
        self.env = env or {}


class MockInput:
    """Mock task input"""
    def __init__(self, params=None, memento=None):
        self.name = "test_agent_tool"
        self.params = params or MockParams()
        self.memento = memento
        self.rundir = "/tmp/test_rundir"
        self.srcdir = "/tmp/test_srcdir"


@pytest.mark.asyncio
async def test_basic_command_validation():
    """Test basic command validation with valid command"""
    params = MockParams(command="python", args=["--version"])
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].type == "std.AgentTool"
    assert result.output[0].command == "python"
    assert result.output[0].args == ["--version"]
    assert result.output[0].url == ""
    assert result.changed is True


@pytest.mark.asyncio
async def test_command_not_found():
    """Test error handling when command is not found"""
    params = MockParams(command="nonexistent_command")
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value=None):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 1
    assert len(result.markers) >= 1
    assert any("Command not found" in m.msg for m in result.markers)
    assert result.markers[0].severity == SeverityE.Error


@pytest.mark.asyncio
async def test_missing_command_parameter():
    """Test error when required command parameter is missing"""
    params = MockParams(command="")
    input_obj = MockInput(params=params)
    
    result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 1
    assert len(result.markers) >= 1
    assert any("command' is required" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_install_command_success():
    """Test successful execution of install command"""
    params = MockParams(
        command="node",
        args=["server.js"],
        install_command="npm install test-package"
    )
    input_obj = MockInput(params=params)
    
    # Mock subprocess.run for installation
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "Installation successful"
    mock_result.stderr = ""
    
    with patch('shutil.which', return_value='/usr/bin/node'), \
         patch('subprocess.run', return_value=mock_result), \
         patch('builtins.open', create=True):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 0
    assert result.changed is True  # Installation causes change
    assert result.memento.install_executed is True
    assert result.memento.install_hash is not None


@pytest.mark.asyncio
async def test_install_command_failure():
    """Test handling of failed install command"""
    params = MockParams(
        command="node",
        install_command="npm install nonexistent-package"
    )
    input_obj = MockInput(params=params)
    
    # Mock subprocess.run for failed installation
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Package not found"
    
    with patch('subprocess.run', return_value=mock_result), \
         patch('builtins.open', create=True):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 1
    assert any("Installation command failed" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_install_command_timeout():
    """Test handling of install command timeout"""
    import subprocess
    
    params = MockParams(
        command="node",
        install_command="npm install --slow"
    )
    input_obj = MockInput(params=params)
    
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 300)):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 1
    assert any("timed out" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_memento_prevents_reinstall():
    """Test that memento prevents re-running installation"""
    import hashlib
    
    install_cmd = "npm install test-package"
    install_hash = hashlib.sha256(install_cmd.encode()).hexdigest()
    
    # Create memento showing installation already done
    memento = {
        "command_hash": "abc123",
        "install_executed": True,
        "install_hash": install_hash
    }
    
    params = MockParams(
        command="node",
        install_command=install_cmd
    )
    input_obj = MockInput(params=params, memento=memento)
    
    with patch('shutil.which', return_value='/usr/bin/node'), \
         patch('subprocess.run') as mock_run:
        result = await AgentToolStdio(None, input_obj)
    
    # Installation should NOT be called
    mock_run.assert_not_called()
    assert result.status == 0


@pytest.mark.asyncio
async def test_install_command_rerun_on_change():
    """Test that installation re-runs if command changes"""
    import hashlib
    
    old_install = "npm install old-package"
    old_hash = hashlib.sha256(old_install.encode()).hexdigest()
    
    # Memento with old installation
    memento = {
        "command_hash": "abc123",
        "install_executed": True,
        "install_hash": old_hash
    }
    
    # New installation command
    new_install = "npm install new-package"
    params = MockParams(
        command="node",
        install_command=new_install
    )
    input_obj = MockInput(params=params, memento=memento)
    
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "Installed"
    mock_result.stderr = ""
    
    with patch('shutil.which', return_value='/usr/bin/node'), \
         patch('subprocess.run', return_value=mock_result) as mock_run, \
         patch('builtins.open', create=True):
        result = await AgentToolStdio(None, input_obj)
    
    # Installation SHOULD be called due to change
    mock_run.assert_called_once()
    assert result.status == 0
    assert result.changed is True


@pytest.mark.asyncio
async def test_memento_tracking():
    """Test memento creation and hash tracking"""
    import hashlib
    
    params = MockParams(command="python", args=["-m", "server"])
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.memento is not None
    assert result.memento.command_hash is not None
    
    # Verify hash matches expected
    expected_hash = hashlib.sha256("python -m server".encode()).hexdigest()
    assert result.memento.command_hash == expected_hash


@pytest.mark.asyncio
async def test_changed_detection():
    """Test that changed flag is set correctly"""
    import hashlib
    
    # First run - no memento
    params = MockParams(command="python")
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result1 = await AgentToolStdio(None, input_obj)
    
    assert result1.changed is True
    
    # Second run - same command, with memento
    command_hash = hashlib.sha256("python ".encode()).hexdigest()
    memento = {
        "command_hash": command_hash,
        "install_executed": False
    }
    input_obj2 = MockInput(params=params, memento=memento)
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result2 = await AgentToolStdio(None, input_obj2)
    
    assert result2.changed is False
    
    # Third run - different args, should be changed
    params3 = MockParams(command="python", args=["--version"])
    input_obj3 = MockInput(params=params3, memento=memento)
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result3 = await AgentToolStdio(None, input_obj3)
    
    assert result3.changed is True


@pytest.mark.asyncio
async def test_complex_args():
    """Test handling of complex argument lists"""
    params = MockParams(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace", "--readonly"]
    )
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value='/usr/bin/npx'):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 0
    assert result.output[0].args == ["-y", "@modelcontextprotocol/server-filesystem", "/workspace", "--readonly"]


@pytest.mark.asyncio
async def test_env_parameter_preserved():
    """Test that env parameter is accepted (even if not used in validation)"""
    params = MockParams(
        command="node",
        args=["server.js"],
        env={"NODE_ENV": "production", "DEBUG": "true"}
    )
    input_obj = MockInput(params=params)
    
    with patch('shutil.which', return_value='/usr/bin/node'):
        result = await AgentToolStdio(None, input_obj)
    
    assert result.status == 0
    # Env is stored in params but not in output (used at runtime)


@pytest.mark.asyncio
async def test_invalid_memento_handling():
    """Test graceful handling of invalid memento data"""
    params = MockParams(command="python")
    # Invalid memento structure
    input_obj = MockInput(params=params, memento={"invalid": "data"})
    
    with patch('shutil.which', return_value='/usr/bin/python'):
        result = await AgentToolStdio(None, input_obj)
    
    # Should still succeed despite invalid memento
    assert result.status == 0
    assert result.changed is True
