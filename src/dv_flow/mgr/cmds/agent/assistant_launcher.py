#****************************************************************************
#* assistant_launcher.py
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
"""Assistant launcher - launches AI assistants in interactive mode."""

import logging
import os
import subprocess
import sys
from typing import List, Optional
from .context_builder import AgentContext
from ...std.ai_assistant import ASSISTANT_REGISTRY, get_available_assistant_name


class AssistantLauncher:
    """Launches AI assistant with context in interactive mode.
    
    This differs from the Prompt task which runs assistants non-interactively.
    The agent command launches an interactive terminal session with the assistant.
    """
    
    _log = logging.getLogger("AssistantLauncher")
    
    def __init__(self, assistant_name: Optional[str] = None, model: Optional[str] = None):
        """Initialize launcher.
        
        Args:
            assistant_name: Name of assistant to use ('copilot', 'codex', etc.)
                          If None, auto-detects available assistant
            model: Model name to use (assistant-specific)
        """
        self.assistant_name = assistant_name
        self.model = model
    
    def launch(self, context: AgentContext, system_prompt: str, working_dir: str, rundir: str) -> int:
        """Launch assistant in interactive mode.
        
        Args:
            context: Agent context with tools/skills/etc
            system_prompt: Generated system prompt
            working_dir: Working directory for the assistant (CWD)
            rundir: Run directory where we can store temp files
        
        Returns:
            Exit code from assistant process
        
        Raises:
            RuntimeError: If assistant is not available or launch fails
        """
        # Determine which assistant to use
        if self.assistant_name:
            assistant_name = self.assistant_name
        else:
            assistant_name = get_available_assistant_name()
            if not assistant_name:
                raise RuntimeError(
                    "No AI assistant available. Please install GitHub Copilot CLI or OpenAI Codex CLI."
                )
            self._log.info(f"Auto-detected assistant: {assistant_name}")
        
        # Get assistant class
        if assistant_name not in ASSISTANT_REGISTRY:
            raise RuntimeError(f"Unknown assistant: {assistant_name}")
        
        assistant_cls = ASSISTANT_REGISTRY[assistant_name]
        assistant = assistant_cls()
        
        # Check availability
        is_available, error_msg = assistant.check_available()
        if not is_available:
            raise RuntimeError(f"Assistant '{assistant_name}' not available: {error_msg}")
        
        # Write system prompt to a file in rundir
        import time
        timestamp = int(time.time() * 1000)
        context_file = os.path.join(rundir, f'agent_context_{timestamp}.md')
        
        self._log.debug(f"Writing system prompt to {context_file}")
        os.makedirs(rundir, exist_ok=True)
        with open(context_file, 'w') as f:
            f.write(system_prompt)
        
        try:
            # Build launch command based on assistant type
            if assistant_name == 'copilot':
                cmd = self._build_copilot_command(context_file, working_dir, context)
            elif assistant_name == 'codex':
                cmd = self._build_codex_command(context_file, working_dir, context)
            else:
                raise RuntimeError(f"Interactive mode not supported for assistant: {assistant_name}")
            
            # Launch in interactive mode
            self._log.info(f"Launching {assistant_name} in interactive mode")
            self._log.debug(f"Command: {' '.join(cmd)}")
            
            # Run interactively - pass through stdin/stdout/stderr
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            
            return result.returncode
            
        except KeyboardInterrupt:
            self._log.info("Interrupted by user")
            return 130  # Standard exit code for SIGINT
        except Exception as e:
            raise RuntimeError(f"Failed to launch assistant: {e}") from e
        finally:
            # Clean up context file
            if os.path.exists(context_file):
                self._log.debug(f"Removing {context_file}")
                os.remove(context_file)
    
    def _build_copilot_command(self, context_file: str, working_dir: str, 
                               context: AgentContext) -> List[str]:
        """Build command for GitHub Copilot CLI in interactive mode.
        
        Args:
            context_file: Path to file containing system prompt
            working_dir: Working directory
            context: Agent context
        
        Returns:
            Command line as list of strings
        """
        cmd = ['copilot']
        
        # Use -i flag to start interactive mode with an initial prompt
        # The prompt tells copilot to read the context file
        initial_prompt = f"Please read and understand the context from {context_file}"
        cmd.extend(['-i', initial_prompt])
        
        # Enable all tools for non-interactive execution
        cmd.append('--allow-all-tools')
        
        # Add accessible directory
        cmd.extend(['--add-dir', working_dir])
        
        # Add model if specified
        if self.model:
            cmd.extend(['--model', self.model])
        
        return cmd
    
    def _build_codex_command(self, context_file: str, working_dir: str,
                            context: AgentContext) -> List[str]:
        """Build command for OpenAI Codex CLI in interactive mode.
        
        Args:
            context_file: Path to file containing system prompt
            working_dir: Working directory
            context: Agent context
        
        Returns:
            Command line as list of strings
        """
        cmd = ['codex']
        
        # Use interactive mode with initial prompt
        initial_prompt = f"Please read and understand the context from {context_file}"
        cmd.extend(['-i', initial_prompt])
        
        # Add writable root
        cmd.extend(['--writable-root', working_dir])
        
        # Add model if specified
        if self.model:
            cmd.extend(['--model', self.model])
        
        return cmd
