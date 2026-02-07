#****************************************************************************
#* agent.py
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

_log = logging.getLogger("Agent")

class DuckTypedOutput(BaseModel):
    """Duck-typed output object that supports arbitrary fields"""
    class Config:
        extra = "allow"  # Allow arbitrary fields
    
    def __init__(self, **data):
        super().__init__(**data)

# Default system prompt template
# Notes on variable expansion:
# - ${{ resources }} is expanded at runtime with agent skills, references, personas
# - ${{ inputs }} is expanded at runtime by this task with JSON of input data
# - ${{ name }} is expanded at runtime by this task with the task name
# - ${{ result_file }} is expanded at runtime by this task with the result filename
DEFAULT_SYSTEM_PROMPT = """You are an AI assistant helping with a DV Flow task.

## Task Information
Task name: ${{ name }}

${{ resources }}

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

class AgentMemento(BaseModel):
    """Memento for tracking agent execution"""
    prompt_hash: str
    result_hash: Optional[str] = None
    timestamp: float = 0.0


async def Agent(runner, input) -> TaskDataResult:
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
    _log.debug(f"Agent task: {input.name}")
    
    status = 0
    markers = []
    changed = False
    output = []
    
    # Step 1: Build agent context from input data items (for MCP tools)
    agent_context = None
    try:
        # Extract agent resources directly from input data items
        if input.inputs:
            from ..cmds.agent.context_builder import AgentContext
            agent_context = AgentContext()
            
            for inp in input.inputs:
                # Check the type field to determine resource type
                inp_type = getattr(inp, 'type', None)
                
                if not inp_type:
                    continue
                
                # Check if we have access to loader to look up type tags
                if hasattr(runner, 'runner') and hasattr(runner.runner, 'builder'):
                    builder = runner.runner.builder
                    if hasattr(builder, 'loader'):
                        # Look up the type definition to check its tags
                        type_def = builder.loader.findType(inp_type)
                        if type_def:
                            # Get type tags
                            type_tags = getattr(type_def, 'tags', []) or []
                            tag_names = set()
                            for tag in type_tags:
                                if hasattr(tag, 'name'):
                                    tag_names.add(tag.name)
                                else:
                                    tag_names.add(str(tag))
                            
                            # Extract based on tag type
                            if 'std.AgentToolTag' in tag_names:
                                tool = {
                                    'name': getattr(inp, 'src', ''),
                                    'desc': getattr(inp, 'desc', ''),  # Extract desc from data item
                                    'command': str(getattr(inp, 'command', '')),
                                    'args': list(getattr(inp, 'args', [])),
                                    'url': str(getattr(inp, 'url', ''))
                                }
                                agent_context.tools.append(tool)
                                _log.debug(f"Added tool from input: {tool['name']}")
                            
                            elif 'std.AgentSkillTag' in tag_names:
                                skill = {
                                    'name': getattr(inp, 'src', ''),
                                    'desc': getattr(inp, 'desc', ''),  # Extract desc from data item
                                    'files': list(getattr(inp, 'files', [])),
                                    'content': str(getattr(inp, 'content', '')),
                                    'urls': list(getattr(inp, 'urls', []))
                                }
                                agent_context.skills.append(skill)
                                _log.debug(f"Added skill from input: {skill['name']}")
                            
                            elif 'std.AgentPersonaTag' in tag_names:
                                persona = {
                                    'name': getattr(inp, 'src', ''),
                                    'desc': getattr(inp, 'desc', ''),  # Extract desc from data item
                                    'persona': str(getattr(inp, 'persona', ''))
                                }
                                agent_context.personas.append(persona)
                                _log.debug(f"Added persona from input: {persona['name']}")
                            
                            elif 'std.AgentReferenceTag' in tag_names:
                                reference = {
                                    'name': getattr(inp, 'src', ''),
                                    'desc': getattr(inp, 'desc', ''),  # Extract desc from data item
                                    'files': list(getattr(inp, 'files', [])),
                                    'content': str(getattr(inp, 'content', '')),
                                    'urls': list(getattr(inp, 'urls', []))
                                }
                                agent_context.references.append(reference)
                                _log.debug(f"Added reference from input: {reference['name']}")
            
            if agent_context.tools or agent_context.skills or agent_context.personas or agent_context.references:
                _log.info(f"Agent context built from inputs: {len(agent_context.tools)} tools, "
                         f"{len(agent_context.skills)} skills, {len(agent_context.personas)} personas, "
                         f"{len(agent_context.references)} references")
            else:
                agent_context = None  # No resources found
    except Exception as e:
        _log.warning(f"Failed to build agent context from inputs: {e}")
        import traceback
        _log.debug(traceback.format_exc())
        # Continue without context - not fatal
    
    # Step 2: Determine which assistant to use
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
                full_prompt, runner, model, assistant_config, agent_context
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
        
        memento = AgentMemento(
            prompt_hash=prompt_hash,
            result_hash=result_hash,
            timestamp=os.path.getmtime(result_path) if os.path.exists(result_path) else 0.0
        )
    
    _log.debug(f"Agent task complete: status={status}, changed={changed}, output_count={len(output)}")
    
    return TaskDataResult(
        status=status,
        changed=changed,
        output=output,
        markers=markers,
        memento=memento
    )


def _build_prompt_context(input):
    """Separate agent resources from regular inputs.
    
    Args:
        input: Task input with inputs list
    
    Returns:
        Tuple of (resources dict, regular_inputs list)
    """
    resources = {
        'skills': [],
        'personas': [],
        'references': [],
        'tools': []
    }
    regular_inputs = []
    
    for inp in input.inputs:
        inp_type = getattr(inp, 'type', '')
        
        # Check if this is an agent resource
        if inp_type == 'std.AgentSkill':
            resources['skills'].append({
                'name': getattr(inp, 'src', ''),
                'desc': getattr(inp, 'desc', ''),
                'files': list(getattr(inp, 'files', [])),
                'content': str(getattr(inp, 'content', '')),
                'urls': list(getattr(inp, 'urls', []))
            })
        elif inp_type == 'std.AgentReference':
            resources['references'].append({
                'name': getattr(inp, 'src', ''),
                'desc': getattr(inp, 'desc', ''),
                'files': list(getattr(inp, 'files', [])),
                'content': str(getattr(inp, 'content', '')),
                'urls': list(getattr(inp, 'urls', []))
            })
        elif inp_type == 'std.AgentPersona':
            resources['personas'].append({
                'name': getattr(inp, 'src', ''),
                'desc': getattr(inp, 'desc', ''),
                'persona': str(getattr(inp, 'persona', ''))
            })
        elif inp_type == 'std.AgentTool':
            # Tools handled separately via MCP config
            resources['tools'].append({
                'name': getattr(inp, 'src', ''),
                'desc': getattr(inp, 'desc', ''),
                'command': str(getattr(inp, 'command', '')),
                'args': list(getattr(inp, 'args', [])),
                'url': str(getattr(inp, 'url', ''))
            })
        else:
            # Regular input (FileSet, etc)
            regular_inputs.append(inp)
    
    return resources, regular_inputs


def _format_resources_section(resources):
    """Format agent resources as human-readable documentation.
    
    Args:
        resources: Dict with 'skills', 'personas', 'references', 'tools' keys
    
    Returns:
        Markdown-formatted string
    """
    lines = []
    
    if resources['skills']:
        lines.append("## Available Skills")
        lines.append("")
        lines.append("The following skills provide specialized capabilities:")
        lines.append("")
        
        for skill in resources['skills']:
            lines.append(f"### {skill['name']}")
            if skill['desc']:
                lines.append(skill['desc'])
                lines.append("")
            
            # File pointers (full paths)
            if skill['files']:
                lines.append("**Documentation files:**")
                for file_path in skill['files']:
                    lines.append(f"- `{file_path}`")
                lines.append("")
                lines.append("*Use the `view` tool to read these files when needed.*")
                lines.append("")
            
            # Inline content (if provided)
            if skill['content']:
                lines.append("**Quick Reference:**")
                lines.append("```")
                lines.append(skill['content'])
                lines.append("```")
                lines.append("")
            
            # URLs
            if skill['urls']:
                lines.append("**External Resources:**")
                for url in skill['urls']:
                    lines.append(f"- {url}")
                lines.append("")
    
    if resources['references']:
        lines.append("## Reference Documentation")
        lines.append("")
        lines.append("The following reference materials are available:")
        lines.append("")
        
        for ref in resources['references']:
            lines.append(f"### {ref['name']}")
            if ref['desc']:
                lines.append(ref['desc'])
                lines.append("")
            
            if ref['files']:
                lines.append("**Reference files:**")
                for file_path in ref['files']:
                    lines.append(f"- `{file_path}`")
                lines.append("")
                lines.append("*Use the `view` tool to read sections as needed.*")
                lines.append("")
            
            if ref['content']:
                lines.append("```")
                lines.append(ref['content'])
                lines.append("```")
                lines.append("")
            
            if ref['urls']:
                lines.append("**External References:**")
                for url in ref['urls']:
                    lines.append(f"- {url}")
                lines.append("")
    
    if resources['personas']:
        lines.append("## Persona")
        lines.append("")
        for persona in resources['personas']:
            if persona.get('persona'):
                lines.append(persona['persona'])
                lines.append("")
    
    return "\n".join(lines) if lines else ""


def _format_inputs_section(regular_inputs):
    """Format regular inputs without pydantic metadata.
    
    Args:
        regular_inputs: List of input data items (not agent resources)
    
    Returns:
        JSON string with cleaned input data
    """
    if not regular_inputs:
        return "[]"
    
    inputs_list = []
    for inp in regular_inputs:
        try:
            # Extract only meaningful fields, not pydantic internals
            clean_item = {
                'type': getattr(inp, 'type', ''),
                'src': getattr(inp, 'src', ''),
            }
            
            # Add seq if present
            if hasattr(inp, 'seq'):
                clean_item['seq'] = getattr(inp, 'seq', 0)
            
            # Add type-specific fields
            inp_type = clean_item['type']
            
            if inp_type == 'std.FileSet':
                clean_item['filetype'] = getattr(inp, 'filetype', '')
                clean_item['files'] = getattr(inp, 'files', [])
                clean_item['basedir'] = getattr(inp, 'basedir', '')
                # Only include non-empty optional fields
                if incdirs := getattr(inp, 'incdirs', []):
                    clean_item['incdirs'] = incdirs
                if defines := getattr(inp, 'defines', []):
                    clean_item['defines'] = defines
                if attributes := getattr(inp, 'attributes', []):
                    clean_item['attributes'] = attributes
            else:
                # For unknown types, try model_dump if available
                if hasattr(inp, 'model_dump'):
                    dumped = inp.model_dump()
                    # Remove pydantic internals
                    for key, value in dumped.items():
                        if not key.startswith('model_') and key not in ['type', 'src', 'seq']:
                            clean_item[key] = value
                elif hasattr(inp, 'dict'):
                    dumped = inp.dict()
                    for key, value in dumped.items():
                        if not key.startswith('model_') and key not in ['type', 'src', 'seq']:
                            clean_item[key] = value
                else:
                    # Last resort - iterate attributes
                    for attr in dir(inp):
                        if attr.startswith('_') or attr in ['type', 'src', 'seq']:
                            continue
                        if attr.startswith('model_'):
                            continue
                        if callable(getattr(inp, attr, None)):
                            continue
                        value = getattr(inp, attr, None)
                        if value is not None and value != '' and value != []:
                            clean_item[attr] = value
            
            inputs_list.append(clean_item)
        except Exception as e:
            # If we can't serialize an input, raise with context
            raise ValueError(f"Failed to serialize input: {e}") from e
    
    return json.dumps(inputs_list, indent=2)


def _build_prompt(input) -> str:
    """Build the complete prompt from template and variables"""
    
    # Get system prompt template
    # Note: ${{ inputs }}, ${{ name }}, ${{ resources }} literals are preserved by loader
    # and need to be expanded at runtime here
    system_prompt = input.params.system_prompt if input.params.system_prompt else DEFAULT_SYSTEM_PROMPT
    
    # Get user prompt
    user_prompt = input.params.user_prompt if input.params.user_prompt else ""
    
    # Build variable context
    result_file = input.params.result_file if input.params.result_file else f"{input.name}.result.json"
    
    # Separate and format resources vs regular inputs
    resources, regular_inputs = _build_prompt_context(input)
    
    # Format resources as human-readable documentation
    resources_section = _format_resources_section(resources)
    
    # Format regular inputs cleanly (no pydantic metadata)
    inputs_json = _format_inputs_section(regular_inputs)
    
    # Expand runtime variables in system prompt
    # These are runtime-only and preserved as literals by the loader
    system_prompt = system_prompt.replace("${{ resources }}", resources_section)
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
