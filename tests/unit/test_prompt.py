import pytest
import json
import os
from pathlib import Path
from dv_flow.mgr.std.prompt import (
    Prompt,
    _build_prompt,
    _parse_result_file,
    DEFAULT_SYSTEM_PROMPT
)
from dv_flow.mgr import TaskDataResult, TaskMarker, SeverityE


class MockParams:
    def __init__(self):
        self.system_prompt = "Test prompt with inputs: ${{ inputs }}"
        self.user_prompt = "Do something"
        self.result_file = "result.json"
        self.assistant = "mock"
        self.test_param = "value123"


class MockInput:
    def __init__(self):
        self.name = "test_task"
        self.params = MockParams()
        self.inputs = []
        self.rundir = "/tmp/test"
        self.changed = False
        self.srcdir = "/tmp/src"


def test_build_prompt_basic():
    """Test basic prompt template expansion"""
    input = MockInput()
    prompt = _build_prompt(input)
    
    assert "inputs:" in prompt
    assert "Do something" in prompt


def test_build_prompt_with_inputs():
    """Test prompt building with inputs"""
    input = MockInput()
    input.params.system_prompt = "Inputs: ${{ inputs }}"
    
    # Add mock inputs
    class MockDataItem:
        def __init__(self):
            self.type = "std.FileSet"
            self.files = ["test.py"]
    
    input.inputs = [MockDataItem()]
    
    prompt = _build_prompt(input)
    
    assert "std.FileSet" in prompt
    assert "test.py" in prompt


def test_build_prompt_default_system():
    """Test using default system prompt"""
    input = MockInput()
    input.params.system_prompt = ""
    
    prompt = _build_prompt(input)
    
    # Should use default prompt with comprehensive schema
    assert "You are an AI assistant" in prompt
    assert "## Required Output" in prompt
    assert "You MUST create a JSON file" in prompt
    assert "FileSet Output Schema" in prompt
    assert "The task will FAIL if the result file is missing" in prompt


def test_build_prompt_no_user_prompt():
    """Test building prompt without user prompt"""
    input = MockInput()
    input.params.user_prompt = ""
    
    prompt = _build_prompt(input)
    
    # Should not have "User Request:" section
    assert "User Request:" not in prompt


def test_build_prompt_result_file_expansion():
    """Test that result_file variable is expanded"""
    input = MockInput()
    input.params.system_prompt = "Write to ${{ result_file }}"
    input.params.result_file = "custom.json"
    
    prompt = _build_prompt(input)
    
    assert "Write to custom.json" in prompt


def test_parse_valid_result(tmp_path):
    """Test parsing valid result file"""
    result_file = tmp_path / "result.json"
    result_data = {
        "status": 0,
        "changed": True,
        "output": [{"type": "std.FileSet", "files": ["test.py"]}],
        "markers": []
    }
    
    with open(result_file, "w") as f:
        json.dump(result_data, f)
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is not None
    assert status == "ok"
    assert parsed["status"] == 0
    assert parsed["changed"] is True
    assert len(parsed["output"]) == 1


def test_parse_missing_result(tmp_path):
    """Test parsing missing result file"""
    result_file = tmp_path / "nonexistent.json"
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is None
    assert status == "missing"


def test_parse_invalid_json(tmp_path):
    """Test parsing invalid JSON result"""
    result_file = tmp_path / "result.json"
    
    with open(result_file, "w") as f:
        f.write("{ invalid json")
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is None
    assert status == "invalid_json"


def test_parse_empty_result(tmp_path):
    """Test parsing empty result file"""
    result_file = tmp_path / "result.json"
    
    with open(result_file, "w") as f:
        f.write("")
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is None
    assert status == "invalid_json"


def test_parse_result_not_object(tmp_path):
    """Test result that's not a JSON object"""
    result_file = tmp_path / "result.json"
    
    with open(result_file, "w") as f:
        json.dump([1, 2, 3], f)
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is None
    assert status == "not_object"


def test_parse_result_with_markers(tmp_path):
    """Test parsing result with markers"""
    result_file = tmp_path / "result.json"
    result_data = {
        "status": 0,
        "changed": True,
        "output": [],
        "markers": [
            {
                "msg": "Test message",
                "severity": "info"
            }
        ]
    }
    
    with open(result_file, "w") as f:
        json.dump(result_data, f)
    
    markers = []
    parsed, status = _parse_result_file(str(result_file), markers)
    
    assert parsed is not None
    assert status == "ok"
    assert len(parsed["markers"]) == 1
    assert parsed["markers"][0]["msg"] == "Test message"


@pytest.mark.asyncio
async def test_prompt_missing_assistant(tmp_path):
    """Test handling of missing assistant"""
    input = MockInput()
    input.params.assistant = "nonexistent"
    input.rundir = str(tmp_path)
    
    result = await Prompt(None, input)
    
    assert result.status == 1
    assert len(result.markers) > 0
    assert "Unknown AI assistant" in result.markers[0].msg


@pytest.mark.asyncio
async def test_prompt_build_failure(tmp_path):
    """Test handling of prompt build failure"""
    input = MockInput()
    input.rundir = str(tmp_path)
    input.params.assistant = "copilot"  # Use valid assistant
    
    # Create an input object that will fail to serialize
    class BadInput:
        def model_dump(self):
            raise ValueError("Cannot serialize input")
        def dict(self):
            raise ValueError("Cannot serialize input")
    
    input.inputs = [BadInput()]
    
    result = await Prompt(None, input)
    
    assert result.status == 1
    assert any("Failed to build prompt" in m.msg for m in result.markers)


@pytest.mark.asyncio
async def test_prompt_retry_logic(tmp_path):
    """Test retry logic when assistant fails and then succeeds"""
    from dv_flow.mgr.std.ai_assistant import AIAssistantBase, ASSISTANT_REGISTRY
    from typing import Tuple
    
    class FlakeyAssistant(AIAssistantBase):
        def __init__(self):
            self.call_count = 0
            
        async def execute(self, prompt: str, runner, model: str, config: dict) -> Tuple[int, str, str]:
            self.call_count += 1
            # Fail first 2 attempts, succeed on 3rd
            if self.call_count < 3:
                return 1, f"Attempt {self.call_count} failed", "Error occurred"
            else:
                # Create result file on success
                result_file = os.path.join(runner.rundir, "result.json")
                result_data = {
                    "status": 0,
                    "changed": True,
                    "output": [],
                    "markers": []
                }
                with open(result_file, "w") as f:
                    json.dump(result_data, f)
                return 0, f"Success on attempt {self.call_count}", ""
        
        def check_available(self) -> Tuple[bool, str]:
            return True, ""
    
    # Register test assistant
    ASSISTANT_REGISTRY["flakey"] = FlakeyAssistant
    
    input = MockInput()
    input.rundir = str(tmp_path)
    input.params.assistant = "flakey"
    input.params.max_retries = 5
    
    result = await Prompt(input, input)
    
    # Should succeed after retries
    assert result.status == 0
    assert result.changed is True
    
    # Cleanup
    del ASSISTANT_REGISTRY["flakey"]


@pytest.mark.asyncio
async def test_prompt_max_retries_exceeded(tmp_path):
    """Test that assistant fails after max retries exceeded"""
    from dv_flow.mgr.std.ai_assistant import AIAssistantBase, ASSISTANT_REGISTRY
    from typing import Tuple
    
    class AlwaysFailAssistant(AIAssistantBase):
        def __init__(self):
            self.call_count = 0
            
        async def execute(self, prompt: str, runner, model: str, config: dict) -> Tuple[int, str, str]:
            self.call_count += 1
            return 1, f"Attempt {self.call_count} failed", "Always fails"
        
        def check_available(self) -> Tuple[bool, str]:
            return True, ""
    
    # Register test assistant
    ASSISTANT_REGISTRY["always_fail"] = AlwaysFailAssistant
    
    input = MockInput()
    input.rundir = str(tmp_path)
    input.params.assistant = "always_fail"
    input.params.max_retries = 3
    
    result = await Prompt(input, input)
    
    # Should fail after max retries
    assert result.status == 1
    assert any("failed after" in m.msg for m in result.markers)
    
    # Cleanup
    del ASSISTANT_REGISTRY["always_fail"]


@pytest.mark.asyncio
async def test_prompt_retry_on_empty_output_with_status_zero(tmp_path):
    """Test that assistant retries when status=0 but no result and empty output log"""
    from dv_flow.mgr.std.ai_assistant import AIAssistantBase, ASSISTANT_REGISTRY
    from typing import Tuple
    
    class EmptyOutputAssistant(AIAssistantBase):
        def __init__(self):
            self.call_count = 0
            
        async def execute(self, prompt: str, runner, model: str, config: dict) -> Tuple[int, str, str]:
            self.call_count += 1
            
            # Create empty copilot_output.log file
            output_log = os.path.join(runner.rundir, 'copilot_output.log')
            with open(output_log, 'w') as f:
                f.write("")  # Empty file
            
            # First two attempts: status=0 but no result file (should trigger retry)
            if self.call_count <= 2:
                return 0, "", ""  # status=0, no result file, empty output log
            
            # Third attempt: succeed with result file (using correct filename)
            result_file = os.path.join(runner.rundir, "result.json")
            result_data = {
                "changed": True,
                "output": [{"type": "std.FileSet", "files": ["test.txt"]}]
            }
            with open(result_file, "w") as f:
                json.dump(result_data, f)
            return 0, f"Success on attempt {self.call_count}", ""
        
        def check_available(self) -> Tuple[bool, str]:
            return True, ""
    
    # Register test assistant
    ASSISTANT_REGISTRY["empty_output"] = EmptyOutputAssistant
    
    input = MockInput()
    input.rundir = str(tmp_path)
    input.params.assistant = "empty_output"
    input.params.max_retries = 5
    
    result = await Prompt(input, input)
    
    # Should succeed after retries
    assert result.status == 0
    assert result.changed is True
    
    # Cleanup
    del ASSISTANT_REGISTRY["empty_output"]


@pytest.mark.asyncio
async def test_prompt_fail_on_empty_output_after_max_retries(tmp_path):
    """Test that assistant fails when status=0, no result, and empty output log persist"""
    from dv_flow.mgr.std.ai_assistant import AIAssistantBase, ASSISTANT_REGISTRY
    from typing import Tuple
    
    class AlwaysEmptyAssistant(AIAssistantBase):
        def __init__(self):
            self.call_count = 0
            
        async def execute(self, prompt: str, runner, model: str, config: dict) -> Tuple[int, str, str]:
            self.call_count += 1
            
            # Create empty copilot_output.log file
            output_log = os.path.join(runner.rundir, 'copilot_output.log')
            with open(output_log, 'w') as f:
                f.write("")  # Empty file
            
            # Always return status=0 but no result (should fail after max retries)
            return 0, "", ""
        
        def check_available(self) -> Tuple[bool, str]:
            return True, ""
    
    # Register test assistant
    ASSISTANT_REGISTRY["always_empty"] = AlwaysEmptyAssistant
    
    input = MockInput()
    input.rundir = str(tmp_path)
    input.params.assistant = "always_empty"
    input.params.max_retries = 3
    
    result = await Prompt(input, input)
    
    # Should fail after max retries
    assert result.status == 1
    assert any("empty output log" in m.msg for m in result.markers)
    
    # Cleanup
    del ASSISTANT_REGISTRY["always_empty"]
