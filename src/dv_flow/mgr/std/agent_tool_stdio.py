#****************************************************************************
#* agent_tool_stdio.py
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
#****************************************************************************
import os
import logging
import hashlib
import shutil
import subprocess
from pydantic import BaseModel
from typing import Optional
from dv_flow.mgr import TaskDataResult, TaskMarker, SeverityE

_log = logging.getLogger("AgentToolStdio")


class AgentToolStdioMemento(BaseModel):
    """Memento for tracking AgentToolStdio execution state"""
    command_hash: str
    install_executed: bool = False
    install_hash: Optional[str] = None


class AgentToolData(BaseModel):
    """Data item for AgentTool output"""
    type: str = "std.AgentTool"
    command: str = ""
    args: list = []
    url: str = ""
    
    model_config = {"extra": "allow"}


async def AgentToolStdio(runner, input) -> TaskDataResult:
    """
    Configure an MCP server using stdio transport.
    
    Parameters:
    - command: Command to execute the MCP server
    - args: List of arguments to pass to the command
    - install_command: Optional installation command to run once
    - env: Optional environment variables for the server
    
    Returns TaskDataResult with AgentTool output data.
    """
    _log.debug(f"AgentToolStdio task: {input.name}")
    
    status = 0
    markers = []
    changed = False
    output = []
    
    # Load existing memento if available
    try:
        ex_memento = AgentToolStdioMemento(**input.memento) if input.memento is not None else None
    except Exception as e:
        _log.warning(f"Failed to load memento: {e}")
        ex_memento = None
    
    # Get parameters
    command = input.params.command if input.params.command else ""
    args = list(input.params.args) if hasattr(input.params, 'args') and input.params.args else []
    install_command = input.params.install_command if hasattr(input.params, 'install_command') and input.params.install_command else ""
    env = dict(input.params.env) if hasattr(input.params, 'env') and input.params.env else {}
    
    # Validate required parameters
    if not command:
        markers.append(TaskMarker(
            msg="Parameter 'command' is required",
            severity=SeverityE.Error
        ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 1: Handle installation if specified
    install_hash = None
    install_executed = ex_memento.install_executed if ex_memento else False
    
    if install_command:
        install_hash = hashlib.sha256(install_command.encode()).hexdigest()
        
        # Check if we need to run installation
        needs_install = (
            not ex_memento or 
            not ex_memento.install_executed or 
            ex_memento.install_hash != install_hash
        )
        
        if needs_install:
            _log.info(f"Running installation command: {install_command}")
            try:
                result = subprocess.run(
                    install_command,
                    shell=True,
                    cwd=input.rundir,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                # Write installation logs
                install_log = os.path.join(input.rundir, "install.log")
                with open(install_log, "w") as f:
                    f.write(f"Command: {install_command}\n")
                    f.write(f"Exit code: {result.returncode}\n\n")
                    f.write("=== STDOUT ===\n")
                    f.write(result.stdout)
                    f.write("\n=== STDERR ===\n")
                    f.write(result.stderr)
                
                if result.returncode != 0:
                    markers.append(TaskMarker(
                        msg=f"Installation command failed with exit code {result.returncode}",
                        severity=SeverityE.Error
                    ))
                    markers.append(TaskMarker(
                        msg=f"Installation stderr: {result.stderr[:200]}",
                        severity=SeverityE.Error
                    ))
                    return TaskDataResult(status=1, markers=markers, changed=False)
                
                _log.info(f"Installation completed successfully")
                install_executed = True
                changed = True
                
            except subprocess.TimeoutExpired:
                markers.append(TaskMarker(
                    msg=f"Installation command timed out after 300 seconds",
                    severity=SeverityE.Error
                ))
                return TaskDataResult(status=1, markers=markers, changed=False)
            except Exception as e:
                markers.append(TaskMarker(
                    msg=f"Failed to execute installation command: {str(e)}",
                    severity=SeverityE.Error
                ))
                _log.exception("Installation failed")
                return TaskDataResult(status=1, markers=markers, changed=False)
    
    # Step 2: Validate command exists
    command_path = shutil.which(command)
    if command_path is None:
        markers.append(TaskMarker(
            msg=f"Command not found: '{command}'. Ensure it is in PATH or use an absolute path.",
            severity=SeverityE.Error
        ))
        if install_command:
            markers.append(TaskMarker(
                msg=f"Command still not found after installation. Check installation logs.",
                severity=SeverityE.Error
            ))
        return TaskDataResult(status=1, markers=markers, changed=False)
    
    _log.debug(f"Command found at: {command_path}")
    
    # Step 3: Create command hash for memento
    command_str = f"{command} {' '.join(str(a) for a in args)}"
    command_hash = hashlib.sha256(command_str.encode()).hexdigest()
    
    # Check if configuration changed
    if ex_memento and ex_memento.command_hash != command_hash:
        changed = True
    elif not ex_memento:
        changed = True
    
    # Step 4: Create output data item
    if runner is not None:
        # Use runner.mkDataItem for proper type registration
        # Get task description from input
        task_desc = getattr(input, 'desc', '') or ''
        tool_data = runner.mkDataItem(
            "std.AgentTool",
            desc=task_desc,
            command=command,
            args=args,
            url=""
        )
    else:
        # Fallback for unit tests without runner
        tool_data = AgentToolData(
            type="std.AgentTool",
            command=command,
            args=args,
            url=""
        )
    
    output = [tool_data]
    
    # Step 5: Create memento
    memento = AgentToolStdioMemento(
        command_hash=command_hash,
        install_executed=install_executed,
        install_hash=install_hash
    )
    
    _log.info(f"AgentToolStdio configured: command={command}, args={args}")
    
    return TaskDataResult(
        status=status,
        changed=changed,
        output=output,
        markers=markers,
        memento=memento
    )
