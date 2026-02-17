#****************************************************************************
#* task_node_while.py
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
class TaskNodeWhile(TaskNodeControl):
    """
    While loop control flow node (pre-condition loop).
    
    Evaluates condition BEFORE each iteration. If condition is false initially,
    the body never executes (may execute 0 times).
    """
    
    _log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskNodeWhile"))
    
    async def do_run(self, runner, rundir, memento=None) -> TaskDataResult:
        """
        Execute the while loop.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            memento: Optional checkpoint state
            
        Returns:
            TaskDataResult from the last completed iteration (or empty if 0 iterations)
        """
        self._log.debug(f"==> while loop: {self.name}, max_iter={self.control_def.max_iter}")
        
        # Initialize state from control_def
        state = dict(self.control_def.state.init) if (self.control_def.state and self.control_def.state.init) else {}
        
        max_iter = self.control_def.max_iter
        last_result = None
        iteration_count = 0
        
        for iteration in range(max_iter):
            # Inject automatic iteration variables
            self._inject_iteration_vars(state, iteration, max_iter)
            
            # PRE-CONDITION: Check condition before executing body
            if not self._eval_condition(self.control_def.cond, state):
                self._log.info(f"while {self.name}: condition false at iteration {iteration}, exiting")
                break
            
            self._log.info(f"while {self.name}: iteration {iteration + 1}/{max_iter}")
            
            # Execute the body for this iteration
            try:
                iteration_result = await self._build_and_run_body(runner, rundir, iteration, state)
                last_result = iteration_result
                iteration_count += 1
                
            except Exception as e:
                self._log.error(f"while {self.name}: iteration {iteration} failed: {e}")
                return TaskDataResult(status=1, output=[])
            
            # Extract state from the iteration output for next iteration
            if iteration_result.output:
                new_state = self._extract_output_state(iteration_result.output)
                
                # Check for _break signal
                if self._check_break_signal(new_state):
                    self._log.info(f"while {self.name}: _break signal detected at iteration {iteration}")
                    state = new_state
                    break
                
                # Apply feedback transformation if configured
                if self.control_def.state and self.control_def.state.feedback:
                    state = self._apply_feedback(new_state)
                else:
                    # Default: pass through the output as next iteration's state
                    state = new_state
        
        else:
            # Loop completed without early exit
            self._log.info(f"while {self.name}: reached max_iter ({max_iter})")
        
        # Package final result
        if last_result:
            self.result = last_result
            self.output = TaskDataOutput(
                changed=last_result.changed if hasattr(last_result, 'changed') else False,
                output=last_result.output,
                dep_m={}
            )
        else:
            # Condition was false from the start - no iterations executed
            self._log.info(f"while {self.name}: condition false initially, 0 iterations executed")
            self.result = TaskDataResult(status=0, output=[])
            self.output = TaskDataOutput(changed=False, output=[], dep_m={})
        
        self._log.debug(f"<== while loop: {self.name}, iterations={iteration_count}, status={self.result.status}")
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
            raise Exception("while loop requires runner with builder access")
        
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
            self._log.warning(f"while {self.name}: no body tasks created for iteration {iteration}")
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
