#****************************************************************************
#* run_tasks.py
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
import logging
from typing import Dict, List, Optional, Union
from pydantic import BaseModel
from ..task_data import TaskDataInput, TaskDataResult, TaskDataOutput, SeverityE

_log = logging.getLogger(__name__)

class RunTasksParams(BaseModel):
    """Parameters for RunTasks task"""
    timeout: Optional[float] = None  # Optional timeout in seconds
    # Note: continue_on_error removed per MSB feedback - use fail-fast

async def RunTasks(ctxt, input: TaskDataInput) -> TaskDataResult:
    """
    Dynamically execute tasks specified in input TaskRunSpec items.
    
    Dynamic tasks are structured as children of the RunTasks task, with
    each getting a unique subdirectory under the RunTasks rundir.
    
    This task:
    1. Collects TaskRunSpec items from inputs
    2. Creates TaskNode for each spec using the builder
    3. Sets up hierarchical structure (parent, rundir)
    4. Sets up dependencies (both batch-local and inflight tasks)
    5. Submits to ctxt.run_subgraph() for execution
    6. Collects outputs from completed tasks
    7. Uses fail-fast: any task failure propagates immediately
    
    Args:
        ctxt: TaskRunCtxt - execution context with run_subgraph capability
        input: TaskDataInput - contains params and TaskRunSpec input items
        
    Returns:
        TaskDataResult with outputs from all dynamic tasks
        
    Raises:
        Exception: If any dynamic task fails (fail-fast behavior)
    """
    _log.debug("--> RunTasks: %s" % input.name)
    
    # Get builder access from runner
    if not hasattr(ctxt.runner, 'builder') or ctxt.runner.builder is None:
        ctxt.error("RunTasks requires runner with builder access")
        return TaskDataResult(status=1, output=[])
    
    builder = ctxt.runner.builder
    
    # Get the RunTasks task's rundir to use as base for children
    # The rundir is passed in via input
    runtasks_rundir = input.rundir
    
    # Extract TaskRunSpec items from inputs
    task_specs = []
    for inp in input.inputs:
        if hasattr(inp, 'type') and inp.type == 'std.TaskRunSpec':
            task_specs.append(inp)
        # Handle nested items (some tasks output lists)
        elif isinstance(inp, list):
            for item in inp:
                if hasattr(item, 'type') and item.type == 'std.TaskRunSpec':
                    task_specs.append(item)
    
    if not task_specs:
        _log.warning("RunTasks: No TaskRunSpec items found in inputs")
        # Return empty success - no work to do
        return TaskDataResult(status=0, output=[])
    
    _log.info("RunTasks: Processing %d TaskRunSpec items" % len(task_specs))
    
    # Get the parent task node (the RunTasks task itself) for hierarchical structure
    # We need to find this task in the runner's tracking
    parent_task_node = None
    if hasattr(ctxt.runner, '_pending_tasks') and input.name in ctxt.runner._pending_tasks:
        parent_task_node = ctxt.runner._pending_tasks[input.name]
        _log.debug(f"Found parent task node: {parent_task_node.name}")
    
    # Phase 1: Create TaskNodes for all specs
    task_nodes = []
    task_name_map = {}  # Maps task_name -> TaskNode for batch-local references
    
    for idx, spec in enumerate(task_specs):
        # Determine task name
        if hasattr(spec, 'task_name') and spec.task_name:
            task_name = spec.task_name
        else:
            # Auto-generate name
            task_name = f"{input.name}_dyn_{idx}"
        
        # Check for required field
        if not hasattr(spec, 'task_type') or not spec.task_type:
            ctxt.error(f"TaskRunSpec missing required 'task_type' field (spec {idx})")
            return TaskDataResult(status=1, output=[])
        
        task_type = spec.task_type
        
        # Extract parameter overrides
        params = {}
        if hasattr(spec, 'params') and spec.params:
            params = spec.params if isinstance(spec.params, dict) else {}
        
        _log.debug(f"Creating TaskNode: type={task_type}, name={task_name}, params={params}")
        
        try:
            # Create the task node
            task_node = builder.mkTaskNode(
                task_type,
                name=task_name,
                **params
            )
            
            # Set up hierarchical structure
            # 1. Set parent reference
            if parent_task_node:
                task_node.parent = parent_task_node
            
            # 2. Set rundir as child of RunTasks
            # rundir is a list of path segments
            if isinstance(runtasks_rundir, list):
                # Append child task name to parent's rundir
                task_node.rundir = runtasks_rundir + [task_name]
            else:
                # Fallback: create new rundir list
                task_node.rundir = [input.name, task_name]
            
            _log.debug(f"Task {task_name} rundir: {task_node.rundir}")
            
            task_nodes.append(task_node)
            task_name_map[task_name] = task_node
            
        except Exception as e:
            ctxt.error(f"Failed to create TaskNode for '{task_type}': {str(e)}")
            return TaskDataResult(status=1, output=[])
    
    # Phase 2: Wire up dependencies
    # Dependencies can reference:
    # - Other TaskRunSpec items in this batch (batch-local)
    # - Tasks already in flight from the static graph (inflight)
    
    for idx, spec in enumerate(task_specs):
        if not hasattr(spec, 'needs') or not spec.needs:
            continue
            
        task_node = task_nodes[idx]
        needs_list = spec.needs if isinstance(spec.needs, list) else [spec.needs]
        
        for need_name in needs_list:
            if not isinstance(need_name, str):
                _log.warning(f"TaskRunSpec needs must be strings, got {type(need_name)}")
                continue
            
            dep_node = None
            
            # First check batch-local references
            if need_name in task_name_map:
                dep_node = task_name_map[need_name]
                _log.debug(f"Resolved batch-local dependency: {task_node.name} -> {need_name}")
            
            # Then check inflight tasks (if runner has pending_tasks)
            elif hasattr(ctxt.runner, '_pending_tasks') and need_name in ctxt.runner._pending_tasks:
                dep_node = ctxt.runner._pending_tasks[need_name]
                _log.debug(f"Resolved inflight dependency: {task_node.name} -> {need_name}")
            
            else:
                ctxt.error(f"TaskRunSpec dependency '{need_name}' not found (referenced by '{task_node.name}')")
                return TaskDataResult(status=1, output=[])
            
            # Add to needs list (node, blocking)
            if dep_node:
                task_node.needs.append((dep_node, False))
    
    # Phase 3: Execute the sub-graph
    _log.info(f"Executing sub-graph with {len(task_nodes)} dynamic tasks")
    
    try:
        # Use the timeout from params if specified and > 0
        timeout = None
        if hasattr(input.params, 'timeout') and input.params.timeout and input.params.timeout > 0:
            timeout = input.params.timeout
        
        results = await ctxt.run_subgraph(
            task_nodes,
            name=f"{input.name}_subgraph",
            timeout=timeout
        )
        
        _log.info(f"Sub-graph execution completed successfully")
        
    except Exception as e:
        # Fail-fast: any error propagates immediately
        ctxt.error(f"Dynamic task execution failed: {str(e)}")
        return TaskDataResult(status=1, output=[])
    
    # Phase 4: Collect outputs
    # Results is either a single TaskDataOutput or a list
    output_items = []
    
    if isinstance(results, list):
        for result in results:
            if result and hasattr(result, 'output'):
                output_items.extend(result.output)
    elif results and hasattr(results, 'output'):
        output_items.extend(results.output)
    
    _log.debug(f"RunTasks collected {len(output_items)} output items")
    
    return TaskDataResult(
        status=0,
        output=output_items
    )
