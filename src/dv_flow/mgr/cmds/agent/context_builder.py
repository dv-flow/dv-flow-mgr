#****************************************************************************
#* context_builder.py
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
"""Context builder - collects agent context from task references."""

import asyncio
import logging
import os
import shutil
import sys
from typing import List, Set, Dict, Any, Optional
from dataclasses import dataclass, field
from ...task_graph_builder import TaskGraphBuilder
from ...task_runner import TaskSetRunner
from ...task_listener_log import TaskListenerLog
from ...task_listener_progress import TaskListenerProgress
from ...task_listener_progress_bar import TaskListenerProgressBar


@dataclass
class AgentContext:
    """Container for agent context data."""
    
    skills: List[Dict[str, Any]] = field(default_factory=list)
    personas: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    references: List[Dict[str, Any]] = field(default_factory=list)
    project_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for JSON serialization."""
        return {
            'project': self.project_info,
            'skills': self.skills,
            'personas': self.personas,
            'tools': self.tools,
            'references': self.references
        }


class AgentContextBuilder:
    """Collects agent context from task references.
    
    This class:
    1. Resolves task references to task definitions
    2. Builds and executes task graph to evaluate tasks
    3. Extracts agent resources from task results
    4. Resolves files and URLs to actual content
    """
    
    _log = logging.getLogger("AgentContextBuilder")
    
    def __init__(self, pkg, loader, rundir: str, ui_mode: str = 'log', clean: bool = False):
        """Initialize context builder.
        
        Args:
            pkg: Root package
            loader: Package loader
            rundir: Run directory for task execution
            ui_mode: UI mode for task execution ('log', 'progress', 'tui')
            clean: Whether to clean rundir before execution
        """
        self.pkg = pkg
        self.loader = loader
        self.rundir = rundir
        self.ui_mode = ui_mode
        self.clean = clean
    
    def build_context(self, task_refs: List[str]) -> AgentContext:
        """Build agent context from task references.
        
        Args:
            task_refs: List of task reference strings (e.g., ['PiratePersona', 'SwordSkill'])
        
        Returns:
            AgentContext with collected resources
        
        Raises:
            Exception: If task resolution or execution fails
        """
        # Resolve task references to task names
        task_names = self._resolve_task_refs(task_refs)
        
        if not task_names:
            raise ValueError(f"No tasks found matching references: {task_refs}")
        
        self._log.debug(f"Resolved task references to: {task_names}")
        
        # Execute tasks to get their results
        task_results = self._execute_tasks(task_names)
        
        # Extract agent resources from task results
        context = self._extract_resources(task_results)
        
        # Add project information
        context.project_info = self._get_project_info()
        
        return context
    
    def _resolve_task_refs(self, task_refs: List[str]) -> List[str]:
        """Resolve task references to full task names.
        
        Args:
            task_refs: Task references (short names or full names)
        
        Returns:
            List of full task names
        """
        resolved = []
        
        for ref in task_refs:
            # Try to find the task
            task_name = None
            
            # Check if it's already a full name
            if ref in self.pkg.task_m:
                task_name = ref
            else:
                # Try as short name in root package
                full_name = f"{self.pkg.name}.{ref}"
                if full_name in self.pkg.task_m:
                    task_name = full_name
                else:
                    # Search for task with matching short name
                    for tn, task in self.pkg.task_m.items():
                        short = tn.split('.')[-1]
                        if short == ref:
                            task_name = tn
                            break
            
            if task_name:
                resolved.append(task_name)
            else:
                raise ValueError(f"Task not found: {ref}")
        
        return resolved
    
    def _execute_tasks(self, task_names: List[str]) -> Dict[str, Any]:
        """Execute tasks and return their results.
        
        Args:
            task_names: List of task names to execute
        
        Returns:
            Dictionary mapping task names to task node objects with results
        """
        # Clean rundir if requested
        if self.clean and os.path.exists(self.rundir):
            self._log.debug(f"Cleaning rundir: {self.rundir}")
            shutil.rmtree(self.rundir)
        
        # Ensure rundir exists
        os.makedirs(self.rundir, exist_ok=True)
        
        # Create task listener based on UI mode
        if self.ui_mode == 'progress':
            listener = TaskListenerProgress()
        elif self.ui_mode == 'progressbar':
            listener = TaskListenerProgressBar(message="Initializing...")
        else:
            listener = TaskListenerLog()
        
        # Build task graph
        self._log.debug("Building task graph")
        builder = TaskGraphBuilder(
            root_pkg=self.pkg,
            rundir=self.rundir,
            loader=self.loader,
            marker_l=listener.marker
        )
        
        # Create runner
        runner = TaskSetRunner(rundir=self.rundir, builder=builder)
        runner.add_listener(listener.event)
        
        # Build task nodes
        task_nodes = []
        for task_name in task_names:
            # Ensure full task name
            if '.' not in task_name:
                task_name = f"{self.pkg.name}.{task_name}"
            
            # CLI/Agent usage: allow root package prefix
            task_node = builder.mkTaskNode(task_name, allow_root_prefix=True)
            task_nodes.append(task_node)
        
        self._log.debug(f"Executing {len(task_nodes)} task node(s)")
        
        # Run tasks synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(runner.run(task_nodes))
        finally:
            loop.close()
        
        if runner.status != 0:
            raise RuntimeError(f"Task execution failed with status: {runner.status}")
        
        # Collect all executed task nodes (including dependencies)
        # The runner has executed all dependencies, so we need to collect them
        task_results = {}
        
        # Helper function to collect task node and its dependencies recursively
        def collect_task_node(node):
            if node.name not in task_results:
                task_results[node.name] = node
                # Collect dependencies from needs field
                for dep_tuple in getattr(node, 'needs', []) or []:
                    # needs is List[Tuple[TaskNode,bool]]
                    if isinstance(dep_tuple, tuple) and len(dep_tuple) > 0:
                        dep_node = dep_tuple[0]
                        collect_task_node(dep_node)
                    else:
                        # Sometimes it might just be the node
                        collect_task_node(dep_tuple)
        
        # Start with root task nodes
        for node in task_nodes:
            collect_task_node(node)
        
        return task_results
    
    def _extract_resources(self, task_results: Dict[str, Any]) -> AgentContext:
        """Extract agent resources from executed tasks.
        
        Args:
            task_results: Dictionary of task names to task node objects
        
        Returns:
            AgentContext with extracted resources
        """
        context = AgentContext()
        
        # Process each task node and its results
        for task_name, task_node in task_results.items():
            self._log.debug(f"Extracting resources from task node: {task_name}")
            
            # Get the task definition from the node
            # TaskNodeLeaf has taskdef field
            task = getattr(task_node, 'taskdef', None)
            if task is None:
                self._log.debug(f"No taskdef found for {task_name}")
                continue
            
            # Check if the task uses a type with agent tags
            uses_type = getattr(task, 'uses', None)
            if uses_type is None:
                self._log.debug(f"Task {task_name} has no uses type")
                continue
            
            uses_type_name = uses_type.name if hasattr(uses_type, 'name') else str(uses_type)
            
            # Get the type tags
            type_tags = getattr(uses_type, 'tags', []) or []
            tag_names = set()
            for tag in type_tags:
                if hasattr(tag, 'name'):
                    tag_names.add(tag.name)
                else:
                    tag_names.add(str(tag))
            
            self._log.debug(f"Task {task_name} uses type {uses_type_name} with tags: {tag_names}")
            
            # Extract based on tag type (pass task_node for params access)
            if 'std.AgentSkillTag' in tag_names:
                skill = self._extract_skill(task, task_node)
                if skill:
                    context.skills.append(skill)
            
            if 'std.AgentPersonaTag' in tag_names:
                persona = self._extract_persona(task, task_node)
                if persona:
                    context.personas.append(persona)
            
            if 'std.AgentToolTag' in tag_names:
                tool = self._extract_tool(task, task_node)
                if tool:
                    context.tools.append(tool)
            
            if 'std.AgentReferenceTag' in tag_names:
                reference = self._extract_reference(task, task_node)
                if reference:
                    context.references.append(reference)
        
        return context
    
    def _extract_skill(self, task, task_node) -> Optional[Dict[str, Any]]:
        """Extract skill information from task.
        
        Args:
            task: Task definition
            task_node: Task node with resolved params
        """
        skill = {
            'name': task.name,
            'desc': getattr(task, 'desc', '') or '',
            'files': [],
            'content': '',
            'urls': []
        }
        
        # Get resolved parameters from task node
        params = getattr(task_node, 'params', None)
        if params:
            # Extract files
            if hasattr(params, 'files'):
                files_value = getattr(params, 'files', None)
                if files_value:
                    if isinstance(files_value, list):
                        skill['files'] = self._resolve_file_content(files_value)
                    else:
                        skill['files'] = self._resolve_file_content([files_value])
            
            # Extract content
            if hasattr(params, 'content'):
                content_value = getattr(params, 'content', '')
                if content_value:
                    skill['content'] = str(content_value)
            
            # Extract URLs
            if hasattr(params, 'urls'):
                urls_value = getattr(params, 'urls', None)
                if urls_value:
                    if isinstance(urls_value, list):
                        skill['urls'] = [str(u) for u in urls_value]
                    else:
                        skill['urls'] = [str(urls_value)]
        
        return skill
    
    def _extract_persona(self, task, task_node) -> Optional[Dict[str, Any]]:
        """Extract persona information from task."""
        persona = {
            'name': task.name,
            'desc': getattr(task, 'desc', '') or '',
            'persona': ''
        }
        
        # Get persona content from resolved params
        params = getattr(task_node, 'params', None)
        if params and hasattr(params, 'persona'):
            persona_value = getattr(params, 'persona', '')
            if persona_value:
                persona['persona'] = str(persona_value)
        
        # If no explicit persona parameter, use description
        if not persona['persona']:
            persona['persona'] = persona['desc']
        
        return persona
    
    def _extract_tool(self, task, task_node) -> Optional[Dict[str, Any]]:
        """Extract tool/MCP server information from task."""
        tool = {
            'name': task.name,
            'desc': getattr(task, 'desc', '') or '',
            'command': '',
            'args': [],
            'url': ''
        }
        
        params = getattr(task_node, 'params', None)
        if params:
            if hasattr(params, 'command'):
                command_value = getattr(params, 'command', '')
                if command_value:
                    tool['command'] = str(command_value)
            
            if hasattr(params, 'args'):
                args_value = getattr(params, 'args', None)
                if args_value:
                    if isinstance(args_value, list):
                        tool['args'] = [str(a) for a in args_value]
                    else:
                        tool['args'] = [str(args_value)]
            
            if hasattr(params, 'url'):
                url_value = getattr(params, 'url', '')
                if url_value:
                    tool['url'] = str(url_value)
        
        return tool
    
    def _extract_reference(self, task, task_node) -> Optional[Dict[str, Any]]:
        """Extract reference information from task."""
        reference = {
            'name': task.name,
            'desc': getattr(task, 'desc', '') or '',
            'files': [],
            'content': '',
            'urls': []
        }
        
        params = getattr(task_node, 'params', None)
        if params:
            if hasattr(params, 'files'):
                files_value = getattr(params, 'files', None)
                if files_value:
                    if isinstance(files_value, list):
                        reference['files'] = self._resolve_file_content(files_value)
                    else:
                        reference['files'] = self._resolve_file_content([files_value])
            
            if hasattr(params, 'content'):
                content_value = getattr(params, 'content', '')
                if content_value:
                    reference['content'] = str(content_value)
            
            if hasattr(params, 'urls'):
                urls_value = getattr(params, 'urls', None)
                if urls_value:
                    if isinstance(urls_value, list):
                        reference['urls'] = [str(u) for u in urls_value]
                    else:
                        reference['urls'] = [str(urls_value)]
        
        return reference
    
    def _resolve_file_content(self, file_paths: List[str]) -> List[Dict[str, str]]:
        """Resolve file paths and read content.
        
        Args:
            file_paths: List of file paths (may contain variable references)
        
        Returns:
            List of dicts with 'path' and 'content' keys
        """
        files = []
        
        for path in file_paths:
            path_str = str(path)
            
            # Resolve relative to package basedir
            if not os.path.isabs(path_str):
                basedir = getattr(self.pkg, 'basedir', '') or os.getcwd()
                path_str = os.path.join(basedir, path_str)
            
            # Read file content
            try:
                if os.path.exists(path_str):
                    with open(path_str, 'r', encoding='utf-8') as f:
                        content = f.read()
                    files.append({
                        'path': path_str,
                        'content': content
                    })
                else:
                    self._log.warning(f"File not found: {path_str}")
            except Exception as e:
                self._log.warning(f"Failed to read file {path_str}: {e}")
        
        return files
    
    def _get_project_info(self) -> Dict[str, Any]:
        """Get project information."""
        return {
            'name': self.pkg.name,
            'desc': getattr(self.pkg, 'desc', '') or '',
            'basedir': getattr(self.pkg, 'basedir', '') or '',
        }
