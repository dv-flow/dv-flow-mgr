#****************************************************************************
#* task_node_if.py
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
from typing import Any, List
from .task_node_control import TaskNodeControl
from .task_data import TaskDataResult, TaskDataOutput
from .task_def import TaskDef


@dc.dataclass
class TaskNodeIf(TaskNodeControl):
    """
    If/else conditional control flow node.
    
    Evaluates condition at runtime. If true, executes body tasks.
    If false, executes else_body tasks (if present), otherwise passes through.
    """
    
    else_tasks: List[TaskDef] = dc.field(default_factory=list)
    _log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskNodeIf"))
    
    async def do_run(self, runner, rundir, memento=None) -> TaskDataResult:
        """
        Execute the if/else conditional.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            memento: Optional checkpoint state
            
        Returns:
            TaskDataResult from the executed branch (or passthrough if no branch executes)
        """
        self._log.debug(f"==> if: {self.name}, cond={self.control_def.cond}")
        
        # Evaluate the condition
        condition_met = self._eval_condition(self.control_def.cond, self.state)
        
        self._log.info(f"if {self.name}: condition evaluated to {condition_met}")
        
        # Decide which branch to execute
        if condition_met:
            # Execute body (then branch)
            tasks_to_execute = self.body_tasks
            branch_name = "then"
        else:
            # Execute else branch if present
            if self.else_tasks:
                tasks_to_execute = self.else_tasks
                branch_name = "else"
            else:
                # No else branch - pass through inputs
                self._log.info(f"if {self.name}: condition false and no else branch, passing through")
                self.result = TaskDataResult(status=0, output=[])
                self.output = TaskDataOutput(changed=False, output=[], dep_m={})
                return self.result
        
        # Build and execute the selected branch
        try:
            result = await self._build_and_run_branch(runner, rundir, tasks_to_execute, branch_name)
            
            self.result = result
            self.output = TaskDataOutput(
                changed=result.changed if hasattr(result, 'changed') else False,
                output=result.output,
                dep_m={}
            )
            
        except Exception as e:
            self._log.error(f"if {self.name}: {branch_name} branch execution failed: {e}")
            self.result = TaskDataResult(status=1, output=[])
            self.output = TaskDataOutput(changed=False, output=[], dep_m={})
        
        self._log.debug(f"<== if: {self.name}, status={self.result.status}")
        return self.result
    
    async def _build_and_run_branch(self, runner, rundir, tasks: List[TaskDef], branch_name: str) -> TaskDataResult:
        """
        Build and execute a branch (then or else).
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            tasks: List of TaskDef for the branch
            branch_name: "then" or "else" for logging
            
        Returns:
            TaskDataResult from branch execution
        """
        from .task_run_ctxt import TaskRunCtxt
        
        self._log.debug(f"Building {branch_name} branch")
        
        # Get builder from runner
        if not hasattr(runner, 'builder') or runner.builder is None:
            raise Exception("if construct requires runner with builder access")
        
        builder = runner.builder
        
        # Build branch tasks
        branch_nodes = []
        
        for task_def in tasks:
            task_node = builder._buildTaskNode(
                task_def,
                name=f"{self.name}_{branch_name}_{task_def.name or task_def.root or task_def.export or 'task'}",
                srcdir=self.srcdir,
                params=None,
                hierarchical=True,
                eval=None
            )
            
            if task_node:
                task_node.parent = self
                task_node.rundir = [self.name, branch_name] + task_node.rundir
                branch_nodes.append(task_node)
        
        if not branch_nodes:
            self._log.warning(f"if {self.name}: no tasks created for {branch_name} branch")
            return TaskDataResult(status=0, output=[])
        
        # Create run context
        ctxt = TaskRunCtxt(
            runner=runner,
            name=f"{self.name}_{branch_name}",
            rundir=rundir,
            env=runner.env if hasattr(runner, 'env') else {}
        )
        
        # Execute the branch sub-graph
        self._log.info(f"Executing {branch_name} branch with {len(branch_nodes)} tasks")
        
        try:
            result = await ctxt.run_subgraph(
                branch_nodes,
                name=f"{self.name}_{branch_name}_body"
            )
            
            return result if result else TaskDataResult(status=0, output=[])
            
        except Exception as e:
            self._log.error(f"{branch_name} branch execution failed: {e}")
            raise
