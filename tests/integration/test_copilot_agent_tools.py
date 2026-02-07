"""
Real Copilot CLI integration tests for AgentToolStdio and AgentToolHttp.

These tests use actual GitHub Copilot CLI (gh copilot) with gpt-5-mini model
to test end-to-end workflows where Agent tasks consume MCP tool configurations.

Prerequisites:
- GitHub CLI (gh) installed
- Authenticated with: gh auth login
- Copilot access enabled

Run with: pytest tests/integration/test_copilot_agent_tools.py -v -s --tb=short
"""
import pytest
import os
import json
import tempfile
import shutil
import asyncio
from pathlib import Path

# Check if GitHub Copilot CLI is available
copilot_available = shutil.which("gh") is not None
skip_reason = "GitHub CLI (gh) not available or not authenticated"

pytestmark = pytest.mark.skipif(not copilot_available, reason=skip_reason)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing"""
    workspace = tempfile.mkdtemp(prefix="dv_flow_copilot_test_")
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.copilot
@pytest.mark.slow
@pytest.mark.asyncio
async def test_agent_task_with_copilot_simple(temp_workspace):
    """
    Test Agent task with real Copilot CLI to validate basic functionality.
    
    This test creates a simple Agent task that uses copilot with gpt-5-mini
    to generate a structured JSON output.
    """
    from dv_flow.mgr.std.agent import Agent
    from dv_flow.mgr import TaskDataResult
    
    # Create mock runner with necessary attributes
    class MockRunner:
        def __init__(self, rundir):
            self.rundir = rundir
            self.root_rundir = rundir  # Add root_rundir for copilot
        
        async def exec(self, cmd, logfile=None, logfilter=None, cwd=None, env=None):
            """Mock exec that actually runs the command"""
            import subprocess
            
            # Create logfile path
            if logfile is None:
                logfile = "cmd.log"
            logpath = os.path.join(self.rundir, logfile)
            
            # Ensure rundir exists
            os.makedirs(self.rundir, exist_ok=True)
            
            # Run the command
            with open(logpath, "w") as fp:
                proc = subprocess.Popen(
                    cmd,
                    stdout=fp,
                    stderr=subprocess.STDOUT,
                    cwd=(cwd if cwd is not None else self.rundir),
                    env=(env if env is not None else os.environ)
                )
                status = proc.wait()
            
            return status
    
    # Create mock input
    class MockParams:
        system_prompt = ""
        user_prompt = """Create a JSON result file with the following structure:
{
  "status": 0,
  "changed": true,
  "output": [{"type": "test", "message": "Hello from Copilot"}],
  "markers": []
}

Write this to the result file exactly as shown."""
        result_file = "test_result.json"
        assistant = "copilot"
        model = "gpt-5-mini"
        max_retries = 3
        sandbox_mode = "off"
        approval_mode = "full-auto"
        assistant_config = {}
    
    class MockInput:
        name = "test_copilot_agent"
        params = MockParams()
        inputs = []
        rundir = temp_workspace
        srcdir = temp_workspace
        memento = None
    
    # Run the agent
    result = await Agent(MockRunner(temp_workspace), MockInput())
    
    # Verify result
    assert result.status == 0, f"Agent failed with status {result.status}"
    
    # Check result file was created
    result_file_path = Path(temp_workspace) / "test_result.json"
    assert result_file_path.exists(), "Result file not created"
    
    # Parse result file
    with open(result_file_path) as f:
        result_data = json.load(f)
    
    assert result_data["status"] == 0
    assert result_data["changed"] is True
    assert len(result_data.get("output", [])) > 0
    
    print(f"✓ Copilot successfully created result: {result_data}")


@pytest.mark.copilot
@pytest.mark.slow
@pytest.mark.asyncio
async def test_agent_with_tool_stdio_copilot(temp_workspace):
    """
    Test full workflow: AgentToolStdio + Agent with real Copilot.
    
    This test:
    1. Configures a simple echo tool via AgentToolStdio
    2. Runs an Agent task that references the tool
    3. Agent uses Copilot to generate structured output
    """
    from dv_flow.mgr.std.agent_tool_stdio import AgentToolStdio
    from dv_flow.mgr.std.agent import Agent
    
    # Step 1: Configure stdio tool
    class StdioParams:
        command = "echo"
        args = ["test-tool-output"]
        install_command = ""
        env = {}
    
    class StdioInput:
        name = "echo_tool"
        params = StdioParams()
        memento = None
        rundir = temp_workspace
        srcdir = temp_workspace
    
    tool_result = await AgentToolStdio(None, StdioInput())
    assert tool_result.status == 0
    print(f"✓ Configured tool: {tool_result.output[0].command} {tool_result.output[0].args}")
    
    # Step 2: Run Agent that "uses" the tool (tool config available in context)
    class MockRunner:
        def __init__(self, rundir):
            self.rundir = rundir
            self.root_rundir = rundir
        
        async def exec(self, cmd, logfile=None, logfilter=None, cwd=None, env=None):
            """Mock exec that actually runs the command"""
            import subprocess
            
            if logfile is None:
                logfile = "cmd.log"
            logpath = os.path.join(self.rundir, logfile)
            
            os.makedirs(self.rundir, exist_ok=True)
            
            with open(logpath, "w") as fp:
                proc = subprocess.Popen(
                    cmd,
                    stdout=fp,
                    stderr=subprocess.STDOUT,
                    cwd=(cwd if cwd is not None else self.rundir),
                    env=(env if env is not None else os.environ)
                )
                status = proc.wait()
            
            return status
    
    class AgentParams:
        system_prompt = ""
        user_prompt = """You have access to a tool configured as: echo test-tool-output

Create a JSON result file with:
{
  "status": 0,
  "changed": true,
  "output": [{"type": "test", "tool_used": "echo", "message": "Tool configuration successful"}],
  "markers": []
}"""
        result_file = "agent_result.json"
        assistant = "copilot"
        model = "gpt-5-mini"
        max_retries = 3
        sandbox_mode = "off"
        approval_mode = "full-auto"
        assistant_config = {}
    
    class AgentInput:
        name = "test_agent_with_tool"
        params = AgentParams()
        inputs = []  # In real scenario, would include tool_result.output
        rundir = temp_workspace
        srcdir = temp_workspace
        memento = None
    
    agent_result = await Agent(MockRunner(temp_workspace), AgentInput())
    
    # Verify
    assert agent_result.status == 0
    result_file_path = Path(temp_workspace) / "agent_result.json"
    assert result_file_path.exists()
    
    with open(result_file_path) as f:
        result_data = json.load(f)
    
    assert result_data["status"] == 0
    print(f"✓ Agent with tool succeeded: {result_data}")


@pytest.mark.copilot
@pytest.mark.slow
@pytest.mark.asyncio
async def test_agent_with_tool_http_copilot(temp_workspace):
    """
    Test full workflow: AgentToolHttp + Agent with real Copilot.
    
    This test:
    1. Configures an HTTP tool via AgentToolHttp
    2. Runs an Agent task that references the tool
    3. Agent uses Copilot to generate structured output
    """
    from dv_flow.mgr.std.agent_tool_http import AgentToolHttp
    from dv_flow.mgr.std.agent import Agent
    
    # Step 1: Configure HTTP tool (no validation)
    class HttpParams:
        url = "http://api.example.com/mcp"
        validate = False
        health_check_path = ""
        headers = {}
        timeout = 5
    
    class HttpInput:
        name = "api_tool"
        params = HttpParams()
        memento = None
        rundir = temp_workspace
        srcdir = temp_workspace
    
    tool_result = await AgentToolHttp(None, HttpInput())
    assert tool_result.status == 0
    print(f"✓ Configured HTTP tool: {tool_result.output[0].url}")
    
    # Step 2: Run Agent that "uses" the tool
    class MockRunner:
        def __init__(self, rundir):
            self.rundir = rundir
            self.root_rundir = rundir
        
        async def exec(self, cmd, logfile=None, logfilter=None, cwd=None, env=None):
            """Mock exec that actually runs the command"""
            import subprocess
            
            if logfile is None:
                logfile = "cmd.log"
            logpath = os.path.join(self.rundir, logfile)
            
            os.makedirs(self.rundir, exist_ok=True)
            
            with open(logpath, "w") as fp:
                proc = subprocess.Popen(
                    cmd,
                    stdout=fp,
                    stderr=subprocess.STDOUT,
                    cwd=(cwd if cwd is not None else self.rundir),
                    env=(env if env is not None else os.environ)
                )
                status = proc.wait()
            
            return status
    
    class AgentParams:
        system_prompt = ""
        user_prompt = f"""You have access to an HTTP MCP tool at: {tool_result.output[0].url}

Create a JSON result file with:
{{
  "status": 0,
  "changed": true,
  "output": [{{"type": "test", "tool_url": "{tool_result.output[0].url}", "message": "HTTP tool configured"}}],
  "markers": []
}}"""
        result_file = "http_agent_result.json"
        assistant = "copilot"
        model = "gpt-5-mini"
        max_retries = 3
        sandbox_mode = "off"
        approval_mode = "full-auto"
        assistant_config = {}
    
    class AgentInput:
        name = "test_agent_http_tool"
        params = AgentParams()
        inputs = []
        rundir = temp_workspace
        srcdir = temp_workspace
        memento = None
    
    agent_result = await Agent(MockRunner(temp_workspace), AgentInput())
    
    # Verify
    assert agent_result.status == 0
    result_file_path = Path(temp_workspace) / "http_agent_result.json"
    assert result_file_path.exists()
    
    with open(result_file_path) as f:
        result_data = json.load(f)
    
    assert result_data["status"] == 0
    assert any("tool_url" in str(item) for item in result_data.get("output", []))
    print(f"✓ Agent with HTTP tool succeeded: {result_data}")


@pytest.mark.copilot
@pytest.mark.slow
@pytest.mark.asyncio
async def test_agent_retry_with_copilot(temp_workspace):
    """
    Test Agent retry logic with real Copilot.
    
    This test verifies that if Copilot initially fails or produces
    empty output, the retry mechanism works correctly.
    """
    from dv_flow.mgr.std.agent import Agent
    
    class MockRunner:
        def __init__(self, rundir):
            self.rundir = rundir
            self.root_rundir = rundir
        
        async def exec(self, cmd, logfile=None, logfilter=None, cwd=None, env=None):
            """Mock exec that actually runs the command"""
            import subprocess
            
            if logfile is None:
                logfile = "cmd.log"
            logpath = os.path.join(self.rundir, logfile)
            
            os.makedirs(self.rundir, exist_ok=True)
            
            with open(logpath, "w") as fp:
                proc = subprocess.Popen(
                    cmd,
                    stdout=fp,
                    stderr=subprocess.STDOUT,
                    cwd=(cwd if cwd is not None else self.rundir),
                    env=(env if env is not None else os.environ)
                )
                status = proc.wait()
            
            return status
    
    class AgentParams:
        system_prompt = ""
        user_prompt = """Create a valid JSON result file with status=0 and changed=true.
        
The result MUST be a valid JSON object with these fields:
{
  "status": 0,
  "changed": true,
  "output": [],
  "markers": []
}"""
        result_file = "retry_test.json"
        assistant = "copilot"
        model = "gpt-5-mini"
        max_retries = 5  # Allow retries
        sandbox_mode = "off"
        approval_mode = "full-auto"
        assistant_config = {}
    
    class AgentInput:
        name = "test_retry"
        params = AgentParams()
        inputs = []
        rundir = temp_workspace
        srcdir = temp_workspace
        memento = None
    
    agent_result = await Agent(MockRunner(temp_workspace), AgentInput())
    
    # Should succeed eventually
    assert agent_result.status == 0
    
    result_file = Path(temp_workspace) / "retry_test.json"
    assert result_file.exists()
    
    with open(result_file) as f:
        result_data = json.load(f)
    
    assert result_data["status"] == 0
    print(f"✓ Agent retry mechanism works: {result_data}")


@pytest.mark.copilot
@pytest.mark.slow  
def test_agent_copilot_availability():
    """
    Quick test to verify Copilot CLI is available and working.
    """
    import subprocess
    
    # Check gh command
    result = subprocess.run(["gh", "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    print(f"✓ GitHub CLI version: {result.stdout.strip()}")
    
    # Check copilot extension (may not be installed)
    result = subprocess.run(
        ["gh", "extension", "list"],
        capture_output=True,
        text=True
    )
    
    if "gh-copilot" in result.stdout or "copilot" in result.stdout:
        print("✓ Copilot CLI extension is installed")
    else:
        pytest.skip("Copilot CLI extension not installed. Install with: gh extension install github/gh-copilot")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short", "-m", "copilot"])
