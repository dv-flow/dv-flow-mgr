import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from .marker_collector import MarkerCollector


def test_agent_skill_inherits_files_parameter(tmpdir):
    """Test that AgentSkill inherits files, content, and urls from AgentResource/DataItem"""
    flow_dv = """
package:
  name: test_agent
  tasks:
  - name: MySkill
    uses: std.AgentSkill
    with:
      files:
      - skill.md
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    markers = MarkerCollector()
    
    try:
        pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))
        
        # If we get here without error, the parameter was accepted
        print("Package loaded successfully")
        print("Package:\n%s\n" % pkg.dump())
        
        # Verify no errors
        error_markers = [m for m in markers.markers if m.severity.name == "ERROR"]
        assert len(error_markers) == 0, f"Expected no errors, got: {error_markers}"
        
    except Exception as e:
        pytest.fail(f"Failed to load package: {e}\nMarkers: {markers.markers}")


def test_agent_skill_data_item_creation(tmpdir):
    """Test creating an AgentSkill data item with files parameter"""
    flow_dv = """
package:
  name: test_agent
  tasks:
  - name: MySkill
    uses: std.AgentSkill
    with:
      files:
      - skill.md
      content: "test content"
      urls:
      - https://example.com
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    markers = MarkerCollector()
    
    try:
        pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))
        
        print("Package:\n%s\n" % pkg.dump())
        
        # Verify task was loaded successfully
        myskill = pkg.task_m.get('test_agent.MySkill')
        assert myskill is not None, "MySkill task should exist"
        
        # Verify no errors
        error_markers = [m for m in markers.markers if m.severity.name == "ERROR"]
        assert len(error_markers) == 0, f"Expected no errors, got: {error_markers}"
        
    except Exception as e:
        pytest.fail(f"Failed: {e}\nMarkers: {markers.markers}")


def test_agent_tool_inherits_parameters(tmpdir):
    """Test that AgentTool also inherits from AgentResource"""
    flow_dv = """
package:
  name: test_agent
  tasks:
  - name: MyTool
    uses: std.AgentTool
    with:
      files:
      - tool.json
      urls:
      - https://example.com/mcp
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    markers = MarkerCollector()
    
    try:
        pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))
        error_markers = [m for m in markers.markers if m.severity.name == "ERROR"]
        assert len(error_markers) == 0, f"Expected no errors, got: {error_markers}"
        
    except Exception as e:
        pytest.fail(f"Failed to load package: {e}\nMarkers: {markers.markers}")


def test_agent_reference_inherits_parameters(tmpdir):
    """Test that AgentReference also inherits from AgentResource"""
    flow_dv = """
package:
  name: test_agent
  tasks:
  - name: MyRef
    uses: std.AgentReference
    with:
      files:
      - reference.md
      content: "reference content"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    markers = MarkerCollector()
    
    try:
        pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))
        error_markers = [m for m in markers.markers if m.severity.name == "ERROR"]
        assert len(error_markers) == 0, f"Expected no errors, got: {error_markers}"
        
    except Exception as e:
        pytest.fail(f"Failed to load package: {e}\nMarkers: {markers.markers}")
