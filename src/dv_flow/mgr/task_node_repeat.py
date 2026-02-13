#****************************************************************************
#* task_node_repeat.py
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
import dataclasses as dc
import logging
from typing import Any
from .task_node_control import TaskNodeControl
from .task_data import TaskDataResult, TaskDataOutput


@dc.dataclass
class TaskNodeRepeat(TaskNodeControl):
    """
    Repeat loop control flow node (counted loop with early exit).
    
    Executes body exactly `count` times unless `until` condition becomes true
    or _break signal is encountered.
    """
    
    _log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskNodeRepeat"))
    
    async def do_run(self, runner, rundir, memento=None) -> TaskDataResult:
        """
        Execute the repeat loop.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            memento: Optional checkpoint state
            
        Returns:
            TaskDataResult from the last completed iteration
        """
        count = self.control_def.count
        self._log.debug(f"==> repeat loop: {self.name}, count={count}")
        
        # Initialize state from control_def
        state = dict(self.control_def.state.init) if (self.control_def.state and self.control_def.state.init) else {}
        
        last_result = None
        
        for iteration in range(count):
            self._log.info(f"repeat {self.name}: iteration {iteration + 1}/{count}")
            
            # Inject automatic iteration variables
            self._inject_iteration_vars(state, iteration, count)
            
            # Execute the body for this iteration
            try:
                iteration_result = await self._build_and_run_body(runner, rundir, iteration, state)
                last_result = iteration_result
                
            except Exception as e:
                self._log.error(f"repeat {self.name}: iteration {iteration} failed: {e}")
                return TaskDataResult(status=1, output=[])
            
            # Extract state from the iteration output
            if iteration_result.output:
                new_state = self._extract_output_state(iteration_result.output)
                
                # Check for _break signal
                if self._check_break_signal(new_state):
                    self._log.info(f"repeat {self.name}: _break signal detected at iteration {iteration}")
                    state = new_state
                    break
                
                # Check until condition (if present)
                if self.control_def.until:
                    if self._eval_condition(self.control_def.until, new_state):
                        self._log.info(f"repeat {self.name}: until condition satisfied at iteration {iteration}")
                        state = new_state
                        break
                
                # Apply feedback transformation if configured
                if self.control_def.state and self.control_def.state.feedback:
                    state = self._apply_feedback(new_state)
                else:
                    # Default: pass through the output as next iteration's state
                    state = new_state
        
        else:
            # Loop completed all iterations
            self._log.info(f"repeat {self.name}: completed all {count} iterations")
        
        # Package final result
        if last_result:
            self.result = last_result
            self.output = TaskDataOutput(
                changed=last_result.changed if hasattr(last_result, 'changed') else False,
                output=last_result.output,
                dep_m={}
            )
        else:
            # Should not happen since count > 0
            self.result = TaskDataResult(status=0, output=[])
            self.output = TaskDataOutput(changed=False, output=[], dep_m={})
        
        self._log.debug(f"<== repeat loop: {self.name}, status={self.result.status}")
        return self.result
    
    async def _build_and_run_body(self, runner, rundir, iteration: int, state: dict) -> TaskDataResult:
        """
        Build the body sub-graph for an iteration and execute it.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            iteration: Current iteration number (0-indexed)
            state: Current state dictionary to inject into body tasks
            
        Returns:
            TaskDataResult from body execution
        """
        from .task_run_ctxt import TaskRunCtxt
        
        self._log.debug(f"Building body for iteration {iteration}")
        
        # Get builder from runner
        if not hasattr(runner, 'builder') or runner.builder is None:
            raise Exception("repeat loop requires runner with builder access")
        
        builder = runner.builder
        
        # Build body tasks for this iteration
        body_nodes = []
        
        for task_def in self.body_tasks:
            task_node = builder._buildTaskNode(
                task_def,
                name=f"{self.name}_iter{iteration}_{task_def.name or task_def.root or task_def.export or 'task'}",
                srcdir=self.srcdir,
                params=None,
                hierarchical=True,
                eval=None
            )
            
            if task_node:
                task_node.parent = self
                task_node.rundir = [self.name, f"iter_{iteration}"] + task_node.rundir
                body_nodes.append(task_node)
        
        if not body_nodes:
            self._log.warning(f"repeat {self.name}: no body tasks created for iteration {iteration}")
            return TaskDataResult(status=0, output=[])
        
        # Create run context
        ctxt = TaskRunCtxt(
            runner=runner,
            name=f"{self.name}_iter{iteration}",
            rundir=rundir,
            env=runner.env if hasattr(runner, 'env') else {}
        )
        
        # Execute the body sub-graph
        self._log.info(f"Executing body with {len(body_nodes)} tasks for iteration {iteration}")
        
        try:
            result = await ctxt.run_subgraph(
                body_nodes,
                name=f"{self.name}_iter{iteration}_body"
            )
            
            return result if result else TaskDataResult(status=0, output=[])
            
        except Exception as e:
            self._log.error(f"Body execution failed for iteration {iteration}: {e}")
            raise
