"""
Integration tests for AgentToolStdio and AgentToolHttp with real AI assistants.

These tests use actual copilot CLI with gpt-5-mini model to test end-to-end
workflows combining MCP tool configuration with Agent execution.

Run with: pytest tests/integration/test_agent_tools_integration.py -v -s
"""
import pytest
import os
import json
import tempfile
import shutil
from pathlib import Path

# Skip all tests if copilot is not available
copilot_available = shutil.which("gh") is not None
skip_reason = "GitHub CLI (gh) not available. Install with: gh auth login"

pytestmark = pytest.mark.skipif(not copilot_available, reason=skip_reason)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing"""
    workspace = tempfile.mkdtemp(prefix="dv_flow_test_")
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def flow_file(temp_workspace):
    """Create a basic flow.yaml file"""
    flow_path = Path(temp_workspace) / "flow.yaml"
    return flow_path


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_tool_stdio_with_echo_command(temp_workspace):
    """
    Test AgentToolStdio with a simple echo command.
    
    This is a minimal test that validates the task can configure a stdio tool
    without requiring complex MCP server installation.
    """
    from dv_flow.mgr.std.agent_tool_stdio import AgentToolStdio
    
    class MockParams:
        command = "echo"
        args = ["Hello from MCP"]
        install_command = ""
        env = {}
    
    class MockInput:
        name = "echo_tool"
        params = MockParams()
        memento = None
        rundir = temp_workspace
        srcdir = temp_workspace
    
    result = await AgentToolStdio(None, MockInput())
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].command == "echo"
    assert result.output[0].args == ["Hello from MCP"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_tool_http_with_mock_server(temp_workspace):
    """
    Test AgentToolHttp with validation disabled (no server needed).
    """
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    
    class MockParams:
        url = "http://localhost:8080/mcp"
        validate = False
        health_check_path = ""
        headers = {}
        timeout = 5
    
    class MockInput:
        name = "http_tool"
        params = MockParams()
        memento = None
        rundir = temp_workspace
        srcdir = temp_workspace
    
    result = await AgentToolHttp(None, MockInput())
    
    assert result.status == 0
    assert len(result.output) == 1
    assert result.output[0].url == "http://localhost:8080/mcp"


@pytest.mark.integration
@pytest.mark.slow
def test_full_workflow_with_filesystem_tool(temp_workspace, flow_file):
    """
    Test complete workflow: AgentToolStdio + Agent task using real copilot.
    
    This test:
    1. Configures filesystem MCP tool via AgentToolStdio
    2. Runs an Agent task that consumes the tool
    3. Verifies the agent can produce structured output
    
    Note: This test requires npx and @modelcontextprotocol/server-filesystem
    to be available. It's marked as 'slow' and may be skipped in CI.
    """
    # Create flow definition
    flow_content = f"""
package:
  name: test_mcp_workflow

  tasks:
    - name: FSAccessTool
      uses: std.AgentToolStdio
      with:
        command: echo
        args:
          - "This is a mock MCP server"

    - name: TestAgent
      uses: std.Agent
      needs: [FSAccessTool]
      with:
        user_prompt: |
          Create a JSON result file with status=0, changed=true, 
          and output containing one item with type='test' and message='success'.
        result_file: test_result.json
        assistant: copilot
        model: gpt-5-mini
        max_retries: 3
"""
    
    flow_file.write_text(flow_content)
    
    # Run the flow using python -m dv_flow.mgr
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run", "TestAgent"],
        cwd=temp_workspace,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    # Check execution succeeded
    assert result.returncode == 0, f"Flow execution failed: {result.stderr}"
    
    # Verify result file was created  
    result_file = Path(temp_workspace) / "rundir" / "test_mcp_workflow.TestAgent" / "test_result.json"
    assert result_file.exists(), f"Result file not created. Files in rundir: {list((Path(temp_workspace) / 'rundir').rglob('*'))}"
    
    # Parse and verify result
    with open(result_file) as f:
        result_data = json.load(f)
    
    assert result_data["status"] == 0
    assert result_data["changed"] is True
    assert len(result_data.get("output", [])) > 0


@pytest.mark.integration
@pytest.mark.slow
def test_agent_with_tool_context(temp_workspace):
    """
    Test that Agent task receives tool configuration in its context.
    
    This test verifies the integration between AgentTool tasks and the
    context builder that extracts tool information for Agent tasks.
    """
    from dv_flow.mgr.cmds.agent.context_builder import AgentContextBuilder
    from dv_flow.mgr.util import loadProjPkgDef
    
    # Create a test package with AgentTool task
    package_content = """package:
  name: test_context

  tasks:
    - name: MyTool
      uses: std.AgentToolStdio
      with:
        command: node
        args: ["mcp-server.js"]
"""
    
    pkg_file = Path(temp_workspace) / "flow.dv"
    pkg_file.write_text(package_content)
    
    # Load package using proper utility
    loader, pkg = loadProjPkgDef(temp_workspace)
    
    assert pkg is not None, "Failed to load package"
    assert pkg.name == "test_context", f"Package name is {pkg.name}, expected test_context"
    
    # Build context
    rundir = Path(temp_workspace) / "rundir"
    rundir.mkdir(exist_ok=True)
    
    builder = AgentContextBuilder(
        pkg=pkg,
        loader=loader,
        rundir=str(rundir),
        ui_mode='log',
        clean=False
    )
    
    # Execute and extract context - use full qualified name
    context = builder.build_context(["test_context.MyTool"])
    
    # Verify tool was extracted
    assert len(context.tools) > 0
    tool = context.tools[0]
    assert tool['command'] == "node"
    assert tool['args'] == ["mcp-server.js"]


@pytest.mark.integration
def test_multiple_tools_composition(temp_workspace):
    """
    Test Agent task with multiple MCP tools configured.
    """
    from dv_flow.mgr.util import loadProjPkgDef
    
    flow_content = """package:
  name: multi_tool_test

  tasks:
    - name: Tool1
      uses: std.AgentToolStdio
      with:
        command: echo
        args: ["tool1"]

    - name: Tool2
      uses: std.AgentToolHttp
      with:
        url: http://localhost:9000
        validate: false

    - name: MultiToolAgent
      uses: std.Agent
      needs: [Tool1, Tool2]
      with:
        user_prompt: "Create result with status=0"
        result_file: result.json
        assistant: copilot
        model: gpt-5-mini
"""
    
    flow_file = Path(temp_workspace) / "flow.dv"
    flow_file.write_text(flow_content)
    
    # Load package using proper utility
    loader, pkg = loadProjPkgDef(temp_workspace)
    
    assert pkg is not None, "Failed to load package"
    assert pkg.name == "multi_tool_test", f"Package name is {pkg.name}, expected multi_tool_test"
    
    # Verify all tasks are defined
    assert "multi_tool_test.Tool1" in pkg.task_m
    assert "multi_tool_test.Tool2" in pkg.task_m
    assert "multi_tool_test.MultiToolAgent" in pkg.task_m


@pytest.mark.integration
@pytest.mark.asyncio
async def test_install_command_execution(temp_workspace):
    """
    Test that install_command actually executes.
    
    Uses a simple echo command to file to verify execution.
    """
    from dv_flow.mgr.std.agent_tool_stdio import AgentToolStdio
    
    marker_file = Path(temp_workspace) / "installed.txt"
    
    class MockParams:
        command = "echo"
        args = ["test"]
        install_command = f"echo 'installed' > {marker_file}"
        env = {}
    
    class MockInput:
        name = "install_test"
        params = MockParams()
        memento = None
        rundir = temp_workspace
        srcdir = temp_workspace
    
    result = await AgentToolStdio(None, MockInput())
    
    assert result.status == 0
    assert result.memento.install_executed is True
    assert marker_file.exists()
    assert marker_file.read_text().strip() == "installed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_http_validation_with_real_url():
    """
    Test HTTP validation against a known public endpoint.
    
    Uses a reliable public API for validation testing.
    """
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    
    class MockParams:
        url = "https://api.github.com"
        validate = True
        health_check_path = ""
        headers = {}
        timeout = 10
    
    class MockInput:
        name = "github_api"
        params = MockParams()
        memento = None
        rundir = tempfile.gettempdir()
        srcdir = tempfile.gettempdir()
    
    result = await AgentToolHttp(None, MockInput())
    
    # Should succeed with real GitHub API
    assert result.status == 0
    assert result.memento.validation_timestamp is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_http_validation_failure_unreachable():
    """
    Test HTTP validation fails appropriately for unreachable URLs.
    """
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    
    class MockParams:
        url = "http://definitely-not-a-real-domain-12345.com"
        validate = True
        health_check_path = ""
        headers = {}
        timeout = 2
    
    class MockInput:
        name = "unreachable"
        params = MockParams()
        memento = None
        rundir = tempfile.gettempdir()
        srcdir = tempfile.gettempdir()
    
    result = await AgentToolHttp(None, MockInput())
    
    # Should fail with connection error
    assert result.status == 1
    assert any("Failed to connect" in m.msg or "timed out" in m.msg for m in result.markers)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s", "--tb=short"])
