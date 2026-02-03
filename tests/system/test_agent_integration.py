import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path


def test_agent_task_loads():
    """Test that the Agent task can be loaded from std package"""
    from dv_flow.mgr import PackageLoader
    
    test_file = Path(__file__).parent / "agent_test" / "flow.dv"
    loader = PackageLoader()
    pkg = loader.load(str(test_file))
    
    assert pkg is not None
    assert pkg.name == "agent_test"
    
    # Check that the task was loaded
    assert "agent_test.simple_agent" in pkg.task_m


def test_agent_task_parameters():
    """Test that Agent task parameters are properly configured"""
    from dv_flow.mgr import PackageLoader
    
    test_file = Path(__file__).parent / "agent_test" / "flow.dv"
    loader = PackageLoader()
    pkg = loader.load(str(test_file))
    
    task = pkg.task_m["agent_test.simple_agent"]
    
    # Check that task has parameter definitions (lazy evaluation)
    assert task.param_defs is not None
    
    # Check that parameters are defined
    assert "user_prompt" in task.param_defs.definitions
    assert "assistant" in task.param_defs.definitions
    
    # Check that std.Agent task was loaded and used
    assert task.uses is not None
    assert task.uses.name == "std.Agent"
    
    # Check that the task has the run method set
    assert task.run == "dv_flow.mgr.std.agent.Agent"


@pytest.mark.skip(reason="Requires GitHub Copilot to be installed and configured")
def test_agent_task_execution():
    """Integration test for Agent task execution (requires copilot)"""
    from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskRunner
    
    test_dir = Path(__file__).parent / "agent_test"
    loader = PackageLoader()
    pkg = loader.load(str(test_dir))
    
    builder = TaskGraphBuilder(pkg)
    node = builder.build("simple_agent")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(rundir=tmpdir)
        result = runner.run(node)
        
        # Check that result file was created
        result_file = Path(tmpdir) / "simple_agent" / "simple_agent.result.json"
        assert result_file.exists()
        
        # Check that prompt file was created
        prompt_file = Path(tmpdir) / "simple_agent" / "simple_agent.prompt.txt"
        assert prompt_file.exists()
