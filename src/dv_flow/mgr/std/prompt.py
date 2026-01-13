#****************************************************************************
#* prompt.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*  
#*   http://www.apache.org/licenses/LICENSE-2.0
#*  
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import os
import json
import logging
import hashlib
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Tuple
from dv_flow.mgr import TaskDataResult, TaskMarker, SeverityE
from .ai_assistant import get_assistant, get_available_assistant_name

_log = logging.getLogger("Prompt")

class DuckTypedOutput(BaseModel):
    """Duck-typed output object that supports arbitrary fields"""
    class Config:
        extra = "allow"  # Allow arbitrary fields
    
    def __init__(self, **data):
        super().__init__(**data)

# Default system prompt template
# Notes on variable expansion:
# - ${{ inputs }} is expanded at runtime by this task with JSON of input data
# - ${{ name }} is expanded at runtime by this task with the task name
# - ${{ result_file }} is expanded at runtime by this task with the result filename
DEFAULT_SYSTEM_PROMPT = """You are an AI assistant helping with a DV Flow task.

## Task Information
Task name: ${{ name }}

## Input Data
The following inputs are available from upstream tasks:
${{ inputs }}

Input data follows this schema:
```json
[
  {
    "type": "std.FileSet",
    "src": "task_name",
    "seq": 0,
    "filetype": "string",
    "basedir": "string",
    "files": ["file1.ext", "file2.ext"],
    "incdirs": ["inc/dir1", "inc/dir2"],
    "defines": ["DEFINE1=value", "DEFINE2"],
    "attributes": ["attr1", "attr2"]
  }
]
```

## Required Output
You MUST create a JSON file at: ${{ result_file }}

The result file must use this exact schema:
```json
{
  "status": 0,
  "changed": true,
  "output": [],
  "markers": []
}
```

### Result Schema Fields:

**status** (integer, required): Exit code. 0 = success, non-zero = failure

**changed** (boolean, required): Whether this task produced new/modified outputs

**output** (array, optional): Output data items to pass to downstream tasks.
Each item should have a "type" field. Common types:

- std.FileSet: For file collections
- std.DataItem: For general data

**markers** (array, optional): Diagnostic messages with severity levels

### FileSet Output Schema:

To output files, use this format in the output array:
```json
{
  "type": "std.FileSet",
  "filetype": "pythonSource",
  "basedir": ".",
  "files": ["generated.py", "utils.py"],
  "incdirs": [],
  "defines": [],
  "attributes": []
}
```

FileSet fields:
- **type** (required): Must be "std.FileSet"
- **filetype** (required): Content type (e.g., "pythonSource", "verilogSource", "cSource", "text")
- **basedir** (required): Base directory for files. Use "." to reference the task's run directory.
- **files** (required): Array of file paths relative to basedir
- **incdirs** (optional): Include directories for compilation
- **defines** (optional): Preprocessor defines
- **attributes** (optional): Additional metadata tags

**Note**: The basedir "." will automatically be resolved to the task's actual run directory path.

### Marker Schema:

```json
{
  "msg": "Diagnostic message text",
  "severity": "info",
  "loc": {
    "path": "file.py",
    "line": 42,
    "pos": 10
  }
}
```

Marker fields:
- **msg** (required): The diagnostic message
- **severity** (required): One of "info", "warning", or "error"
- **loc** (optional): Source location for the marker

## Important Notes

1. The result file MUST be valid JSON
2. The result file MUST be a JSON object (not array or primitive)
3. If you encounter errors, set status to non-zero and add error markers
4. All file paths should be relative to the task's run directory
5. The task will FAIL if the result file is missing or has invalid JSON
"""

class PromptMemento(BaseModel):
    """Memento for tracking prompt execution"""
    prompt_hash: str
    result_hash: Optional[str] = None
    timestamp: float = 0.0


async def Prompt(runner, input) -> TaskDataResult:
    """
    Execute an AI assistant with a prompt
    
    Parameters:
    - system_prompt: Template for system instructions
    - user_prompt: User's prompt content
    - result_file: Name of output JSON file (REQUIRED)
    - assistant: Override default assistant (optional)
    - model: Specify the model to use (optional)
    - assistant_config: Assistant-specific configuration (optional)
    - max_retries: Maximum number of retry attempts on failure (default: 10)
    
    Returns TaskDataResult with status=1 if result file is missing or invalid.
    """
    _log.debug(f"Prompt task: {input.name}")
    
    status = 0
    markers = []
    changed = False
    output = []
    
    # Step 1: Determine which assistant to use
    assistant_name = input.params.assistant if input.params.assistant else None
    
    # Auto-probe for available assistant if none specified
    if not assistant_name:
        assistant_name = get_available_assistant_name()
        if assistant_name:
            _log.info(f"Auto-detected AI assistant: {assistant_name}")
        else:
            markers.append(TaskMarker(
                msg="No AI assistant available. Install copilot or codex CLI.",
                severity=SeverityE.Error
            ))
            return TaskDataResult(status=1, markers=markers, changed=False)
    
    model = input.params.model if hasattr(input.params, 'model') and input.params.model else ""
    
    # Build assistant config, merging sandbox_mode and approval_mode if specified
    assistant_config = dict(input.params.assistant_config) if hasattr(input.params, 'assistant_config') and input.params.assistant_config else {}
    
    # Add sandbox_mode and approval_mode to config for codex
    if hasattr(input.params, 'sandbox_mode') and input.params.sandbox_mode:
        assistant_config['sandbox_mode'] = input.params.sandbox_mode
    if hasattr(input.params, 'approval_mode') and input.params.approval_mode:
        assistant_config['approval_mode'] = input.params.approval_mode
    
    max_retries = input.params.max_retries if hasattr(input.params, 'max_retries') and input.params.max_retries else 10
    
    try:
        assistant = get_assistant(assistant_name)
    except ValueError as e:
        markers.append(TaskMarker(
            msg=str(e),
            severity=SeverityE.Error
        ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 2: Check if assistant is available
    is_available, error_msg = assistant.check_available()
    if not is_available:
        markers.append(TaskMarker(
            msg=f"AI assistant '{assistant_name}' not available: {error_msg}",
            severity=SeverityE.Error
        ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 3: Build the complete prompt
    try:
        full_prompt = _build_prompt(input)
    except Exception as e:
        markers.append(TaskMarker(
            msg=f"Failed to build prompt: {str(e)}",
            severity=SeverityE.Error
        ))
        _log.exception("Prompt build failed")
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 4: Write prompt to file for debugging
    prompt_file = os.path.join(input.rundir, f"{input.name}.prompt.txt")
    try:
        with open(prompt_file, "w") as f:
            f.write(full_prompt)
        _log.debug(f"Wrote prompt to {prompt_file}")
    except IOError as e:
        markers.append(TaskMarker(
            msg=f"Failed to write prompt file: {str(e)}",
            severity=SeverityE.Warning
        ))
    
    # Step 5: Execute the assistant with retry logic
    _log.info(f"Executing AI assistant: {assistant_name} (max_retries={max_retries})")
    
    exec_status = 1
    stdout = ""
    stderr = ""
    attempt = 0
    
    while attempt <= max_retries:
        try:
            if attempt > 0:
                _log.info(f"Retry attempt {attempt}/{max_retries}")
            
            exec_status, stdout, stderr = await assistant.execute(
                full_prompt, runner, model, assistant_config
            )
            
            # Write stdout/stderr to log files
            if stdout:
                stdout_file = os.path.join(input.rundir, f"assistant.stdout.log.{attempt}" if attempt > 0 else "assistant.stdout.log")
                with open(stdout_file, "w") as f:
                    f.write(stdout)
                _log.debug(f"Assistant stdout written to {stdout_file}")
                
            if stderr:
                stderr_file = os.path.join(input.rundir, f"assistant.stderr.log.{attempt}" if attempt > 0 else "assistant.stderr.log")
                with open(stderr_file, "w") as f:
                    f.write(stderr)
                _log.debug(f"Assistant stderr written to {stderr_file}")
            
            if exec_status != 0:
                _log.warning(f"AI assistant exited with status {exec_status} on attempt {attempt}")
                if attempt < max_retries:
                    attempt += 1
                    continue
                else:
                    markers.append(TaskMarker(
                        msg=f"AI assistant failed after {attempt + 1} attempts with status {exec_status}",
                        severity=SeverityE.Error
                    ))
                    if stderr:
                        markers.append(TaskMarker(
                            msg=f"Assistant error: {stderr[:200]}",
                            severity=SeverityE.Error
                        ))
                    status = exec_status
                    break
            else:
                # Status is 0, but check if result was actually produced
                # Check if result file exists and output log is not empty
                result_file = input.params.result_file or f"{input.name}.result.json"
                result_path = os.path.join(input.rundir, result_file)
                
                # Check copilot_output.log for emptiness
                output_log_path = os.path.join(input.rundir, 'copilot_output.log')
                output_log_empty = True
                if os.path.exists(output_log_path):
                    with open(output_log_path, 'r') as f:
                        content = f.read().strip()
                        output_log_empty = len(content) == 0
                
                # If status=0 but no result file AND empty output log, treat as retry scenario
                if not os.path.exists(result_path) and output_log_empty:
                    _log.warning(f"AI assistant exited with status 0 but produced no result file and empty output log on attempt {attempt}")
                    if attempt < max_retries:
                        attempt += 1
                        continue
                    else:
                        markers.append(TaskMarker(
                            msg=f"AI assistant exited with status 0 but produced no result after {attempt + 1} attempts (empty output log)",
                            severity=SeverityE.Error
                        ))
                        status = 1
                        break
                
                # Success - either result exists or there's output to process
                if attempt > 0:
                    _log.info(f"AI assistant succeeded on attempt {attempt}")
                break
                
        except Exception as e:
            _log.warning(f"Assistant execution failed on attempt {attempt}: {str(e)}")
            if attempt < max_retries:
                attempt += 1
                continue
            else:
                markers.append(TaskMarker(
                    msg=f"Failed to execute assistant after {attempt + 1} attempts: {str(e)}",
                    severity=SeverityE.Error
                ))
                _log.exception("Assistant execution failed")
                return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 6: Parse result file (REQUIRED - failure if missing/invalid)
    result_file = input.params.result_file or f"{input.name}.result.json"
    result_path = os.path.join(input.rundir, result_file)
    
    result_data, parse_status = _parse_result_file(result_path, markers)
    
    # STRICT: Missing or invalid result is a hard error
    if result_data is None:
        if parse_status == "missing":
            markers.append(TaskMarker(
                msg=f"Required result file not found: {result_file}. AI assistant must create this file with valid JSON.",
                severity=SeverityE.Error
            ))
        elif parse_status == "invalid_json":
            markers.append(TaskMarker(
                msg=f"Result file contains invalid JSON: {result_file}. Check assistant.stdout.log for details.",
                severity=SeverityE.Error
            ))
        elif parse_status == "not_object":
            markers.append(TaskMarker(
                msg=f"Result file must be a JSON object, not {parse_status}: {result_file}",
                severity=SeverityE.Error
            ))
        else:
            markers.append(TaskMarker(
                msg=f"Failed to parse result file: {result_file}",
                severity=SeverityE.Error
            ))
        
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 7: Extract data from valid result
    output_raw = result_data.get("output", [])
    changed = result_data.get("changed", True)
    
    # Convert output dicts to objects with attribute access (duck typing)
    # Also fix basedir if it's "." to be the actual rundir
    output = []
    for item in output_raw:
        if isinstance(item, dict):
            # Fix basedir for FileSet items: convert "." to actual rundir
            if item.get("type") == "std.FileSet" and item.get("basedir") == ".":
                item["basedir"] = input.rundir
            # Convert dict to duck-typed object with attribute access
            output.append(DuckTypedOutput(**item))
        else:
            output.append(item)
    
    # Add any markers from result
    for marker_data in result_data.get("markers", []):
        try:
            if isinstance(marker_data, dict):
                if "severity" in marker_data and isinstance(marker_data["severity"], str):
                    marker_data["severity"] = SeverityE(marker_data["severity"])
                markers.append(TaskMarker(**marker_data))
            else:
                markers.append(marker_data)
        except Exception as e:
            _log.warning(f"Invalid marker in result: {e}")
            markers.append(TaskMarker(
                msg=f"Invalid marker format in result: {str(marker_data)}",
                severity=SeverityE.Warning
            ))
    
    # Override status if result indicates failure
    if "status" in result_data:
        result_status = result_data["status"]
        if result_status != 0:
            _log.info(f"Result file indicates failure: status={result_status}")
            status = result_status
    
    # Step 8: Build memento
    memento = None
    if status == 0:
        prompt_hash = hashlib.sha256(full_prompt.encode()).hexdigest()
        result_hash = None
        if os.path.exists(result_path):
            with open(result_path, "rb") as f:
                result_hash = hashlib.sha256(f.read()).hexdigest()
        
        memento = PromptMemento(
            prompt_hash=prompt_hash,
            result_hash=result_hash,
            timestamp=os.path.getmtime(result_path) if os.path.exists(result_path) else 0.0
        )
    
    _log.debug(f"Prompt task complete: status={status}, changed={changed}, output_count={len(output)}")
    
    return TaskDataResult(
        status=status,
        changed=changed,
        output=output,
        markers=markers,
        memento=memento
    )


def _build_prompt(input) -> str:
    """Build the complete prompt from template and variables"""
    
    # Get system prompt template
    # Note: ${{ inputs }}, ${{ name }} literals are preserved by loader
    # and need to be expanded at runtime here
    system_prompt = input.params.system_prompt if input.params.system_prompt else DEFAULT_SYSTEM_PROMPT
    
    # Get user prompt
    user_prompt = input.params.user_prompt if input.params.user_prompt else ""
    
    # Build variable context
    result_file = input.params.result_file if input.params.result_file else f"{input.name}.result.json"
    
    # Convert inputs to JSON (runtime expansion)
    inputs_list = []
    for inp in input.inputs:
        if hasattr(inp, 'model_dump'):
            inputs_list.append(inp.model_dump())
        elif hasattr(inp, 'dict'):
            inputs_list.append(inp.dict())
        else:
            inp_dict = {k: v for k, v in inp.__dict__.items() if not k.startswith('_')}
            inputs_list.append(inp_dict)
    inputs_json = json.dumps(inputs_list, indent=2)
    
    # Expand runtime variables in system prompt
    # These are runtime-only and preserved as literals by the loader
    system_prompt = system_prompt.replace("${{ inputs }}", inputs_json)
    system_prompt = system_prompt.replace("${{ name }}", input.name)
    system_prompt = system_prompt.replace("${{ result_file }}", result_file)
    
    # Combine prompts
    if user_prompt:
        full_prompt = f"{system_prompt}\n\nUser Request:\n{user_prompt}"
    else:
        full_prompt = system_prompt
    
    return full_prompt


def _parse_result_file(result_path: str, markers: List[TaskMarker]) -> Tuple[Optional[Dict], str]:
    """
    Parse the JSON result file produced by the AI assistant
    
    Returns: 
        Tuple of (parsed_data, status)
        - parsed_data: Dict if valid, None if invalid
        - status: "ok", "missing", "invalid_json", "not_object", "error"
    """
    if not os.path.exists(result_path):
        _log.debug(f"Result file not found: {result_path}")
        return None, "missing"
    
    try:
        with open(result_path, "r") as f:
            content = f.read()
            
        if not content.strip():
            _log.warning("Result file is empty")
            return None, "invalid_json"
            
        data = json.loads(content)
        
        # Validate basic structure
        if not isinstance(data, dict):
            _log.warning(f"Result file is not a JSON object: {type(data)}")
            return None, "not_object"
        
        _log.debug(f"Parsed result file: {len(data)} keys")
        return data, "ok"
        
    except json.JSONDecodeError as e:
        _log.warning(f"Invalid JSON in result file: {e}")
        return None, "invalid_json"
    except Exception as e:
        _log.error(f"Failed to read result file: {e}")
        return None, "error"
