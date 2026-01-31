#****************************************************************************
#* cmd_agent.py
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
"""Agent command - launches AI assistants with DV Flow context."""

import asyncio
import logging
import os
import sys
from typing import ClassVar, List
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..ext_rgy import ExtRgy
from ..task_listener_log import TaskListenerLog
from ..task_listener_progress import TaskListenerProgress
from ..task_data import SeverityE
from .util import get_rootdir
from .agent.context_builder import AgentContextBuilder
from .agent.prompt_builder import SystemPromptBuilder
from .agent.assistant_launcher import AssistantLauncher


class CmdAgent:
    """Launch an AI assistant with DV Flow context.
    
    This command:
    1. Loads the root package and resolves task references
    2. Evaluates tasks to collect agent resources (skills, personas, tools, references)
    3. Generates system prompt with project context
    4. Launches the AI assistant in interactive mode
    """
    
    _log: ClassVar = logging.getLogger("CmdAgent")
    
    def __call__(self, args):
        """Execute the agent command."""
        
        # Check if we're in server mode (should not happen for agent command)
        server_socket = os.environ.get('DFM_SERVER_SOCKET')
        if server_socket:
            print("Error: 'dfm agent' cannot be run from within an AI assistant session.", 
                  file=sys.stderr)
            return 1
        
        # Determine UI mode for task execution
        ui = getattr(args, 'ui', None)
        if ui is None:
            # Auto-select: progressbar if terminal, log otherwise
            ui = 'progressbar' if sys.stdout.isatty() else 'log'
            # When logging is enabled at INFO or above, prefer plain-text log
            root_level = logging.getLogger().level
            if root_level <= logging.INFO:
                ui = 'log'
        
        # Create listener for package loading
        listener = TaskListenerLog()
        
        # Load project package
        self._log.debug("Loading project package")
        try:
            loader, pkg = loadProjPkgDef(
                get_rootdir(args),
                listener=listener.marker,
                parameter_overrides=parse_parameter_overrides(getattr(args, 'param_overrides', [])),
                config=getattr(args, 'config', None)
            )
        except Exception as e:
            print(f"Error loading project: {e}", file=sys.stderr)
            return 1
        
        if listener.has_severity[SeverityE.Error] > 0:
            print("Error(s) encountered while loading package definition", file=sys.stderr)
            return 1
        
        if pkg is None:
            print("Error: No flow.dv/flow.yaml/flow.toml found in current directory or parent directories",
                  file=sys.stderr)
            return 1
        
        self._log.debug(f"Loaded package: {pkg.name}")
        
        # Check if tasks were specified
        task_refs = getattr(args, 'tasks', [])
        
        # Determine rundir
        rundir = os.path.join(os.getcwd(), "rundir")
        
        # Build context from task references (if any)
        if task_refs:
            self._log.debug(f"Building context from tasks: {task_refs}")
            
            try:
                context_builder = AgentContextBuilder(
                    pkg=pkg,
                    loader=loader,
                    rundir=rundir,
                    ui_mode=ui,
                    clean=getattr(args, 'clean', False)
                )
                
                context = context_builder.build_context(task_refs)
                
            except Exception as e:
                self._log.error(f"Failed to build context: {e}", exc_info=True)
                print(f"Error building context: {e}", file=sys.stderr)
                return 1
        else:
            # No tasks specified - just basic project context
            self._log.debug("No task references specified, using basic project context")
            from .agent.context_builder import AgentContext
            context = AgentContext()
            context.project_info = {
                'name': pkg.name,
                'desc': getattr(pkg, 'desc', '') or '',
                'basedir': getattr(pkg, 'basedir', '') or '',
            }
        
        # Handle --json flag (output context as JSON)
        if getattr(args, 'json', False):
            import json
            print(json.dumps(context.to_dict(), indent=2))
            return 0
        
        # Generate system prompt
        self._log.debug("Generating system prompt")
        prompt_builder = SystemPromptBuilder()
        system_prompt = prompt_builder.build_prompt(context)
        
        # Handle --config-file flag (output config for debugging)
        if config_file := getattr(args, 'config_file', None):
            with open(config_file, 'w') as f:
                f.write(system_prompt)
            print(f"System prompt written to: {config_file}")
            return 0
        
        # Launch assistant
        assistant_name = getattr(args, 'assistant', None)
        model = getattr(args, 'model', None)
        
        self._log.debug(f"Launching assistant (name={assistant_name}, model={model})")
        
        try:
            launcher = AssistantLauncher(
                assistant_name=assistant_name,
                model=model
            )
            
            return launcher.launch(
                context=context,
                system_prompt=system_prompt,
                working_dir=os.getcwd(),
                rundir=rundir
            )
            
        except Exception as e:
            self._log.error(f"Failed to launch assistant: {e}", exc_info=True)
            print(f"Error launching assistant: {e}", file=sys.stderr)
            return 1
    
    def _list_agent_tasks(self, pkg):
        """List tasks that have agent-related tags."""
        agent_tasks = []
        
        if not hasattr(pkg, 'task_m') or not pkg.task_m:
            return
        
        # Look for tasks with agent-related tags
        for task_name, task in pkg.task_m.items():
            # Only show tasks from root package
            if not task_name.startswith(pkg.name + '.'):
                continue
            
            tags = getattr(task, 'tags', []) or []
            tag_names = []
            for tag in tags:
                if hasattr(tag, 'name'):
                    tag_names.append(tag.name)
                else:
                    tag_names.append(str(tag))
            
            # Check if task has agent-related tags
            if any('Agent' in tn for tn in tag_names):
                short_name = task_name.split('.')[-1]
                desc = getattr(task, 'desc', '') or ''
                agent_tasks.append((short_name, desc))
        
        if agent_tasks:
            for name, desc in sorted(agent_tasks):
                if desc:
                    print(f"  {name}: {desc}")
                else:
                    print(f"  {name}")
        else:
            print("  (No agent tasks found)")
