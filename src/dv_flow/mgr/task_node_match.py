#****************************************************************************
#* task_node_match.py
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
class TaskNodeMatch(TaskNodeControl):
    """
    Match (multi-way conditional) control flow node.
    
    Evaluates cases in order. The first matching case's body is executed.
    If no case matches and a default case exists, it is executed.
    Otherwise, inputs pass through.
    """
    
    _log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskNodeMatch"))
    
    async def do_run(self, runner, rundir, memento=None) -> TaskDataResult:
        """
        Execute the match conditional.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            memento: Optional checkpoint state
            
        Returns:
            TaskDataResult from the executed case (or passthrough if no match)
        """
        self._log.debug(f"==> match: {self.name}, cases={len(self.control_def.cases)}")
        
        # Evaluate cases in order
        selected_case = None
        case_index = -1
        
        for idx, case in enumerate(self.control_def.cases):
            # Check if this is the default case
            if case.default:
                # Default case - select if no other case matched
                if selected_case is None:
                    selected_case = case
                    case_index = idx
                    self._log.info(f"match {self.name}: selecting default case (index {idx})")
                break  # Default should be last, but stop here anyway
            
            # Evaluate the when condition
            if case.when:
                if self._eval_condition(case.when, self.state):
                    selected_case = case
                    case_index = idx
                    self._log.info(f"match {self.name}: case {idx} matched (when: {case.when})")
                    break  # First match wins
        
        # If no case matched, pass through
        if selected_case is None:
            self._log.info(f"match {self.name}: no case matched, passing through")
            self.result = TaskDataResult(status=0, output=[])
            self.output = TaskDataOutput(changed=False, output=[], dep_m={})
            return self.result
        
        # Execute the selected case's body
        try:
            result = await self._build_and_run_case(runner, rundir, selected_case, case_index)
            
            self.result = result
            self.output = TaskDataOutput(
                changed=result.changed if hasattr(result, 'changed') else False,
                output=result.output,
                dep_m={}
            )
            
        except Exception as e:
            self._log.error(f"match {self.name}: case {case_index} execution failed: {e}")
            self.result = TaskDataResult(status=1, output=[])
            self.output = TaskDataOutput(changed=False, output=[], dep_m={})
        
        self._log.debug(f"<== match: {self.name}, status={self.result.status}")
        return self.result
    
    async def _build_and_run_case(self, runner, rundir, case, case_index: int) -> TaskDataResult:
        """
        Build and execute a case's body.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory path
            case: ControlCaseDef with body tasks
            case_index: Index of the case (for naming)
            
        Returns:
            TaskDataResult from case execution
        """
        from .task_run_ctxt import TaskRunCtxt
        
        case_name = f"case_{case_index}"
        if case.default:
            case_name = "default"
        
        self._log.debug(f"Building {case_name}")
        
        # Get builder from runner
        if not hasattr(runner, 'builder') or runner.builder is None:
            raise Exception("match construct requires runner with builder access")
        
        builder = runner.builder
        
        # Build case body tasks
        case_nodes = []
        
        for task_def in case.body:
            task_node = builder._buildTaskNode(
                task_def,
                name=f"{self.name}_{case_name}_{task_def.name or task_def.root or task_def.export or 'task'}",
                srcdir=self.srcdir,
                params=None,
                hierarchical=True,
                eval=None
            )
            
            if task_node:
                task_node.parent = self
                task_node.rundir = [self.name, case_name] + task_node.rundir
                case_nodes.append(task_node)
        
        if not case_nodes:
            self._log.warning(f"match {self.name}: no tasks created for {case_name}")
            return TaskDataResult(status=0, output=[])
        
        # Create run context
        ctxt = TaskRunCtxt(
            runner=runner,
            name=f"{self.name}_{case_name}",
            rundir=rundir,
            env=runner.env if hasattr(runner, 'env') else {}
        )
        
        # Execute the case sub-graph
        self._log.info(f"Executing {case_name} with {len(case_nodes)} tasks")
        
        try:
            result = await ctxt.run_subgraph(
                case_nodes,
                name=f"{self.name}_{case_name}_body"
            )
            
            return result if result else TaskDataResult(status=0, output=[])
            
        except Exception as e:
            self._log.error(f"{case_name} execution failed: {e}")
            raise
