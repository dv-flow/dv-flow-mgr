#****************************************************************************
#* dynamic_scheduler.py
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
import dataclasses as dc
import logging
from typing import Any, Dict, List, Set, Union
from .task_node import TaskNode
from .task_data import TaskDataOutput

@dc.dataclass
class DynamicScheduler:
    """
    Mixin for dynamic task scheduling capabilities.
    
    Provides the ability to inject tasks into the execution schedule
    during runtime, enabling dynamic workflow composition.
    """
    
    # Dynamic scheduling state
    _dynamic_enabled: bool = dc.field(default=False, init=False)
    _pending_tasks: Dict[str, TaskNode] = dc.field(default_factory=dict, init=False)
    _task_completion_events: Dict[str, asyncio.Event] = dc.field(default_factory=dict, init=False)
    _dynamic_task_queue: asyncio.Queue = dc.field(default=None, init=False)
    _active_subgraphs: Dict[int, Dict[str, Any]] = dc.field(default_factory=dict, init=False)
    _subgraph_id_counter: int = dc.field(default=0, init=False)
    
    _dynamic_log: logging.Logger = dc.field(default=None, init=False)
    
    def _init_dynamic_scheduler(self):
        """Initialize dynamic scheduler state"""
        if self._dynamic_log is None:
            self._dynamic_log = logging.getLogger("DynamicScheduler")
        if self._dynamic_task_queue is None:
            self._dynamic_task_queue = asyncio.Queue()
    
    async def schedule_subgraph(
        self,
        tasks: Union[TaskNode, List[TaskNode]],
        name: str = None,
        timeout: float = None
    ) -> Union[TaskDataOutput, List[TaskDataOutput]]:
        """
        Dynamically schedule a sub-graph into the current execution.
        
        This method allows a task to submit additional tasks for execution
        during runtime. The sub-graph is integrated into the active schedule,
        respecting dependencies and resource constraints.
        
        Args:
            tasks: TaskNode or list of TaskNodes to execute
            name: Optional name prefix for sub-tasks (for debugging)
            timeout: Optional timeout in seconds (default: None = no timeout)
            
        Returns:
            TaskDataOutput or list of TaskDataOutput from terminal tasks
            
        Raises:
            RuntimeError: If dynamic scheduling is not enabled
            asyncio.TimeoutError: If timeout is exceeded
            Exception: If sub-graph execution fails
        """
        # Validate we're in dynamic scheduling mode
        if not self._dynamic_enabled:
            self._dynamic_log.warning("Dynamic scheduling not enabled, using fallback")
            raise RuntimeError("Dynamic scheduling not enabled")
        
        self._dynamic_log.debug("schedule_subgraph called with %s tasks" % (
            1 if isinstance(tasks, TaskNode) else len(tasks)))
        
        # Create future for this sub-graph
        subgraph_id = self._subgraph_id_counter
        self._subgraph_id_counter += 1
        future = asyncio.Future()
        
        # Build dependency map for sub-graph
        task_list = tasks if isinstance(tasks, list) else [tasks]
        
        try:
            sub_dep_map = self._buildDepMapForSubgraph(task_list)
        except ValueError as e:
            # Circular dependency detected
            self._dynamic_log.error("Failed to build sub-graph: %s" % e)
            raise
        
        # Track this sub-graph
        self._active_subgraphs[subgraph_id] = {
            'tasks': task_list,
            'dep_map': sub_dep_map,
            'future': future,
            'name': name or f"subgraph_{subgraph_id}"
        }
        
        # Inject into scheduling queue
        await self._dynamic_task_queue.put({
            'id': subgraph_id,
            'tasks': task_list,
            'dep_map': sub_dep_map,
            'future': future
        })
        
        self._dynamic_log.debug("Sub-graph %d queued, waiting for completion" % subgraph_id)
        
        # Wait for completion with optional timeout
        try:
            if timeout is not None:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
        except asyncio.TimeoutError:
            self._dynamic_log.error("Sub-graph %d timed out after %.1fs" % (subgraph_id, timeout))
            # Clean up
            if subgraph_id in self._active_subgraphs:
                del self._active_subgraphs[subgraph_id]
            raise
        
        # Clean up
        del self._active_subgraphs[subgraph_id]
        
        self._dynamic_log.debug("Sub-graph %d completed" % subgraph_id)
        return result
    
    def _buildDepMapForSubgraph(
        self, 
        tasks: List[TaskNode]
    ) -> Dict[TaskNode, Set[TaskNode]]:
        """
        Build dependency map for sub-graph tasks.
        
        This includes both internal dependencies (within the sub-graph)
        and external dependencies (on pending tasks in main schedule).
        
        Args:
            tasks: List of tasks in the sub-graph
            
        Returns:
            Dependency map: task -> set of dependencies
        """
        dep_m = {}
        
        # Build internal dependency map
        for task in tasks:
            self._buildDepMap(dep_m, task)
        
        # Check for circular dependencies
        try:
            from toposort import toposort, CircularDependencyError
            list(toposort(dep_m))
        except Exception as e:
            # Circular dependency detected
            self._dynamic_log.error("Circular dependency detected in sub-graph: %s" % e)
            raise ValueError("Circular dependency in sub-graph: %s" % e)
        
        # Check for dependencies on pending tasks in main schedule
        external_deps_found = False
        for task, deps in list(dep_m.items()):
            external_deps = set()
            for dep in list(deps):
                # If dependency is not in the sub-graph but is pending, it's external
                if dep not in dep_m and dep.name in self._pending_tasks:
                    external_deps.add(self._pending_tasks[dep.name])
                    external_deps_found = True
            
            if external_deps:
                # Replace with actual pending task references
                deps.update(external_deps)
        
        if external_deps_found:
            self._dynamic_log.debug("Sub-graph has external dependencies on pending tasks")
        
        return dep_m
    
    def _complete_subgraph(self, subgraph_id: int, done_task_s: Set[TaskNode]):
        """
        Check if a sub-graph is complete and set its result.
        
        Args:
            subgraph_id: ID of the sub-graph to check
            done_task_s: Set of completed tasks
        """
        if subgraph_id not in self._active_subgraphs:
            return
        
        sg_info = self._active_subgraphs[subgraph_id]
        tasks = sg_info['tasks']
        future = sg_info['future']
        
        # Check if all tasks are done (including skipped)
        all_done = all(t in done_task_s for t in tasks)
        
        if all_done and not future.done():
            self._dynamic_log.debug("Sub-graph %d all tasks complete, setting result" % subgraph_id)
            
            # Collect results (even from failed/skipped tasks)
            if len(tasks) == 1:
                result = tasks[0].output if tasks[0].output else TaskDataOutput(changed=False, dep_m={}, output=[])
            else:
                result = [t.output if t.output else TaskDataOutput(changed=False, dep_m={}, output=[]) for t in tasks]
            
            # Set future result
            try:
                future.set_result(result)
                self._dynamic_log.debug("Sub-graph %d future result set" % subgraph_id)
            except Exception as e:
                self._dynamic_log.error("Failed to set sub-graph result: %s" % e)
                if not future.done():
                    future.set_exception(e)
