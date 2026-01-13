#****************************************************************************
#* ai_assistant.py
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
import asyncio
import os
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Tuple, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..task_run_ctxt import TaskRunCtxt

_log = logging.getLogger("AIAssistant")

# Priority order for auto-detection of AI assistants
ASSISTANT_PRIORITY = ["copilot", "codex"]

class AIAssistantBase(ABC):
    """Base class for AI assistant implementations"""
    
    @abstractmethod
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """
        Execute assistant with prompt
        
        Args:
            prompt: The prompt text to send to the assistant
            runner: Task run context for executing subprocesses
            model: The model to use (empty string for default)
            config: Assistant-specific configuration
        
        Returns: 
            Tuple of (status_code, stdout, stderr)
        """
        pass
    
    @abstractmethod
    def check_available(self) -> Tuple[bool, str]:
        """
        Check if assistant is available
        
        Returns: 
            Tuple of (is_available, error_message)
        """
        pass


class MockAssistant(AIAssistantBase):
    """Mock assistant for testing - generates simple responses based on prompt analysis"""
    
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """
        Execute mock assistant - parses prompt and generates appropriate response
        """
        _log.debug("Executing Mock AI Assistant")
        
        try:
            import json
            import re
            
            rundir = runner.rundir
            
            # Extract result file name from prompt
            result_file_match = re.search(r'create a JSON file at: (.+\.json)', prompt)
            result_file = result_file_match.group(1) if result_file_match else "result.json"
            
            # Extract input data from prompt
            inputs_match = re.search(r'## Input Data\s+The following inputs are available[^\[]*(\[.*?\n\])', prompt, re.DOTALL)
            
            response_text = []
            output_data = []
            
            if inputs_match:
                try:
                    inputs_json = inputs_match.group(1)
                    # Clean up the JSON (remove trailing content after closing bracket)
                    bracket_count = 0
                    clean_json = ""
                    for char in inputs_json:
                        clean_json += char
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                break
                    
                    inputs = json.loads(clean_json)
                    
                    response_text.append("Analyzing provided input data:\n")
                    
                    for inp in inputs:
                        if inp.get('type') == 'std.FileSet':
                            files = inp.get('files', [])
                            filetype = inp.get('filetype', 'unknown')
                            response_text.append(f"- Found {len(files)} {filetype} file(s): {', '.join(files)}")
                            
                            # Generate summary for YAML files
                            if filetype == 'yaml' and files:
                                response_text.append("\nPackage summaries:")
                                for f in files:
                                    full_path = os.path.join(inp.get('basedir', '.'), f)
                                    if os.path.exists(full_path):
                                        response_text.append(f"\n{f}:")
                                        with open(full_path, 'r') as yf:
                                            content = yf.read()
                                            if 'name:' in content:
                                                pkg_name_match = re.search(r'name:\s*(\S+)', content)
                                                if pkg_name_match:
                                                    pkg_name = pkg_name_match.group(1)
                                                    response_text.append(f"  Package: {pkg_name}")
                                            response_text.append(f"  A package/project configuration file")
                    
                    # Create summary output file
                    summary_file = "analysis_summary.txt"
                    summary_path = os.path.join(rundir, summary_file)
                    with open(summary_path, 'w') as sf:
                        sf.write('\n'.join(response_text))
                    
                    response_text.append(f"\n\nCreated summary at: {summary_file}")
                    
                    # Add output FileSet
                    output_data.append({
                        "type": "std.FileSet",
                        "filetype": "text",
                        "basedir": ".",
                        "files": [summary_file],
                        "incdirs": [],
                        "defines": [],
                        "attributes": []
                    })
                    
                except Exception as e:
                    response_text.append(f"Error processing inputs: {e}")
            else:
                response_text.append("No input data found in prompt")
            
            # Create result file
            result_path = os.path.join(rundir, result_file)
            result_data = {
                "status": 0,
                "changed": True,
                "output": output_data,
                "markers": []
            }
            
            with open(result_path, 'w') as rf:
                json.dump(result_data, rf, indent=2)
            
            response_text.append(f"\nCreated result file: {result_file}")
            
            stdout = '\n'.join(response_text)
            _log.debug(f"Mock assistant execution complete")
            
            return 0, stdout, ""
            
        except Exception as e:
            _log.error(f"Failed to execute mock assistant: {e}")
            return 1, "", str(e)
    
    def check_available(self) -> Tuple[bool, str]:
        """Mock assistant is always available"""
        return True, ""


class CopilotAssistant(AIAssistantBase):
    """GitHub Copilot CLI implementation"""
    
    @classmethod
    def name(cls) -> str:
        return "copilot"
    
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """
        Execute GitHub Copilot CLI with prompt in non-interactive mode
        
        Note: We use runner.exec() to run the command through the task context
        """
        _log.debug("Executing GitHub Copilot CLI")
        
        try:
            # Write prompt to a file for reference
            prompt_input_file = os.path.join(runner.rundir, "copilot_input.txt")
            with open(prompt_input_file, 'w') as f:
                f.write(prompt)
            
            # Build command - use -p for prompt mode and --allow-all-tools
            cmd = ['copilot', '-p', prompt, '--allow-all-tools', '--silent']
            
            # Add model parameter if specified
            if model:
                cmd.extend(['--model', model])
            
            # Add allowed path for root rundir
            cmd.extend(['--add-dir', runner.root_rundir])
            
            # Execute copilot in non-interactive mode
            status = await runner.exec(
                cmd,
                logfile='copilot_output.log'
            )
            
            # Read stdout and stderr from log file
            stdout_path = os.path.join(runner.rundir, 'copilot_output.log')
            stdout = ""
            stderr = ""
            
            if os.path.exists(stdout_path):
                with open(stdout_path, 'r') as f:
                    stdout = f.read()
            
            _log.debug(f"Copilot execution complete: status={status}")
            
            return status, stdout, stderr
            
        except Exception as e:
            _log.error(f"Failed to execute copilot: {e}")
            raise
    
    def check_available(self) -> Tuple[bool, str]:
        """Check if GitHub Copilot CLI is available"""
        try:
            # Check if 'copilot' command exists
            result = subprocess.run(
                ['which', 'copilot'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, "GitHub Copilot CLI (copilot) not found in PATH"
            
            # Verify copilot responds to --version
            result = subprocess.run(
                ['copilot', '--version'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, "GitHub Copilot CLI found but not responding correctly"
            
            return True, ""
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out while checking GitHub Copilot CLI"
        except FileNotFoundError:
            return False, "GitHub Copilot CLI (copilot) not found in PATH"
        except Exception as e:
            return False, f"Error checking GitHub Copilot CLI: {str(e)}"


class CodexAssistant(AIAssistantBase):
    """OpenAI Codex CLI implementation"""
    
    @classmethod
    def name(cls) -> str:
        return "codex"
    
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """
        Execute OpenAI Codex CLI with prompt in non-interactive mode
        
        Config options:
            sandbox_mode: off | read-only | network-disabled | full (default: off)
            approval_mode: suggest | auto-edit | full-auto (default: full-auto)
        """
        _log.debug("Executing OpenAI Codex CLI")
        
        try:
            # Write prompt to a file for reference
            prompt_input_file = os.path.join(runner.rundir, "codex_input.txt")
            with open(prompt_input_file, 'w') as f:
                f.write(prompt)
            
            # Build command with non-interactive options
            cmd = ['codex', '-q']  # -q for quiet/non-interactive mode
            
            # Add prompt as positional argument
            cmd.append(prompt)
            
            # Add model parameter if specified
            if model:
                cmd.extend(['--model', model])
            
            # Get sandbox mode from config (default: off for workflow execution)
            sandbox_mode = config.get('sandbox_mode', 'off') if config else 'off'
            cmd.extend(['--sandbox', sandbox_mode])
            
            # Get approval mode from config (default: full-auto for workflow execution)
            approval_mode = config.get('approval_mode', 'full-auto') if config else 'full-auto'
            cmd.extend(['--approval-mode', approval_mode])
            
            # Add writable root for the run directory
            cmd.extend(['--writable-root', runner.root_rundir])
            
            # Execute codex in non-interactive mode
            status = await runner.exec(
                cmd,
                logfile='codex_output.log'
            )
            
            # Read stdout from log file
            stdout_path = os.path.join(runner.rundir, 'codex_output.log')
            stdout = ""
            stderr = ""
            
            if os.path.exists(stdout_path):
                with open(stdout_path, 'r') as f:
                    stdout = f.read()
            
            _log.debug(f"Codex execution complete: status={status}")
            
            return status, stdout, stderr
            
        except Exception as e:
            _log.error(f"Failed to execute codex: {e}")
            raise
    
    def check_available(self) -> Tuple[bool, str]:
        """Check if OpenAI Codex CLI is available"""
        try:
            # Check if 'codex' command exists
            result = subprocess.run(
                ['which', 'codex'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, "OpenAI Codex CLI (codex) not found in PATH"
            
            # Verify codex responds to --version
            result = subprocess.run(
                ['codex', '--version'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False, "OpenAI Codex CLI found but not responding correctly"
            
            return True, ""
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out while checking OpenAI Codex CLI"
        except FileNotFoundError:
            return False, "OpenAI Codex CLI (codex) not found in PATH"
        except Exception as e:
            return False, f"Error checking OpenAI Codex CLI: {str(e)}"


class OpenAIAssistant(AIAssistantBase):
    """OpenAI API implementation (placeholder for future)"""
    
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """Execute OpenAI assistant (not yet implemented)"""
        raise NotImplementedError("OpenAI assistant not yet implemented")
    
    def check_available(self) -> Tuple[bool, str]:
        """Check if OpenAI library is available"""
        try:
            import openai
            return True, ""
        except ImportError:
            return False, "openai package not installed. Run: pip install openai"


class ClaudeAssistant(AIAssistantBase):
    """Claude API implementation (placeholder for future)"""
    
    async def execute(self, prompt: str, runner: 'TaskRunCtxt', 
                     model: str, config: dict) -> Tuple[int, str, str]:
        """Execute Claude assistant (not yet implemented)"""
        raise NotImplementedError("Claude assistant not yet implemented")
    
    def check_available(self) -> Tuple[bool, str]:
        """Check if Anthropic library is available"""
        try:
            import anthropic
            return True, ""
        except ImportError:
            return False, "anthropic package not installed. Run: pip install anthropic"


# Registry of available assistants
ASSISTANT_REGISTRY = {
    "mock": MockAssistant,
    "copilot": CopilotAssistant,
    "codex": CodexAssistant,
    "openai": OpenAIAssistant,
    "claude": ClaudeAssistant,
}


def get_assistant(name: str) -> AIAssistantBase:
    """
    Get assistant instance by name
    
    Args:
        name: Name of the assistant (copilot, openai, claude)
        
    Returns:
        Instance of the requested assistant
        
    Raises:
        ValueError: If assistant name is unknown
    """
    if name not in ASSISTANT_REGISTRY:
        available = ", ".join(ASSISTANT_REGISTRY.keys())
        raise ValueError(f"Unknown AI assistant: '{name}'. Available: {available}")
    
    return ASSISTANT_REGISTRY[name]()


def probe_available_assistant() -> Optional[AIAssistantBase]:
    """
    Probe for available AI assistants in priority order.
    
    Priority order: copilot, codex
    
    Returns:
        Instance of the first available assistant, or None if none available
    """
    for name in ASSISTANT_PRIORITY:
        if name in ASSISTANT_REGISTRY:
            assistant = ASSISTANT_REGISTRY[name]()
            is_available, error_msg = assistant.check_available()
            if is_available:
                _log.info(f"Auto-detected AI assistant: {name}")
                return assistant
            else:
                _log.debug(f"Assistant '{name}' not available: {error_msg}")
    
    _log.warning("No AI assistant available in environment")
    return None


def get_available_assistant_name() -> Optional[str]:
    """
    Get the name of the first available AI assistant.
    
    Priority order: copilot, codex
    
    Returns:
        Name of available assistant, or None if none available
    """
    for name in ASSISTANT_PRIORITY:
        if name in ASSISTANT_REGISTRY:
            assistant = ASSISTANT_REGISTRY[name]()
            is_available, _ = assistant.check_available()
            if is_available:
                return name
    return None
