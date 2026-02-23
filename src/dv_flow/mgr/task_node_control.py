#****************************************************************************
#* task_node_control.py
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
from typing import Any, Dict, List
from .task_node_compound import TaskNodeCompound
from .task_def import ControlDef, TaskDef
from .task_data import TaskDataResult
from .expr_eval import ExprEval


@dc.dataclass
class TaskNodeControl(TaskNodeCompound):
    """Base class for runtime control-flow nodes (if, while, do-while, repeat, match)"""
    
    control_def: ControlDef = None
    body_tasks: List[TaskDef] = dc.field(default_factory=list)
    state: Dict[str, Any] = dc.field(default_factory=dict)
    
    _log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskNodeControl"))
    
    def __post_init__(self):
        super().__post_init__()
        # Initialize state from control definition if present
        if self.control_def and self.control_def.state and self.control_def.state.init:
            self.state.update(self.control_def.state.init)
    
    def _eval_condition(self, condition_expr: str, state: Dict[str, Any] = None) -> bool:
        """
        Evaluate a condition expression against the current state.
        
        Args:
            condition_expr: Expression string like "${{ state.score > 0.8 }}"
            state: Optional state dict to use (defaults to self.state)
        
        Returns:
            Boolean result of the condition
        """
        if not condition_expr:
            return True
            
        # Remove ${{ }} wrapper if present
        expr = condition_expr.strip()
        if expr.startswith('${{') and expr.endswith('}}'):
            expr = expr[3:-2].strip()
        
        # Create evaluator with state variables
        evaluator = ExprEval()
        
        # Use provided state or default to self.state
        if state is None:
            state = self.state
        
        # Set state in evaluator
        evaluator.set('state', state)
        
        # Also provide access to input parameters (from needs)
        # This will be populated at runtime when we have actual input data
        if hasattr(self, 'in_params') and self.in_params:
            # Convert in_params list to a dict for easier access
            in_dict = {}
            for param in self.in_params:
                if hasattr(param, 'data'):
                    in_dict.update(param.data)
            evaluator.set('in', in_dict)
        
        # Evaluate the expression
        result = evaluator.eval(expr)
        
        # Handle string boolean results from evaluator
        if isinstance(result, str):
            if result.lower() == 'true':
                return True
            elif result.lower() == 'false':
                return False
        
        # Convert to boolean using evaluator's coercion rules
        return evaluator._to_bool(result)
    
    def _apply_feedback(self, iteration_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply the feedback expression to transform iteration output into next iteration input.
        
        Args:
            iteration_output: Output data from the current iteration
        
        Returns:
            Transformed state for next iteration
        """
        if not self.control_def.state or not self.control_def.state.feedback:
            # No feedback expression - just pass through the output
            return iteration_output
        
        feedback_expr = self.control_def.state.feedback.strip()
        
        # Remove ${{ }} wrapper if present
        if feedback_expr.startswith('${{') and feedback_expr.endswith('}}'):
            feedback_expr = feedback_expr[3:-2].strip()
        
        # Create evaluator with current state
        evaluator = ExprEval()
        evaluator.set('state', iteration_output)
        
        # Evaluate the feedback expression
        # This should return a dict/object representing the new state
        result = evaluator.eval(feedback_expr)
        
        # If result is a JSON string, parse it
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                # Not JSON, just use as-is
                pass
        
        return result if isinstance(result, dict) else iteration_output
    
    def _extract_output_state(self, body_output: List[Any]) -> Dict[str, Any]:
        """
        Extract state data from the body task outputs.
        
        Args:
            body_output: List of output parameter objects from body execution
        
        Returns:
            Dictionary of state values extracted from outputs
        """
        state = {}
        
        for output_item in body_output:
            # Each output item should have 'data' attribute with the actual values
            if hasattr(output_item, 'data') and isinstance(output_item.data, dict):
                state.update(output_item.data)
        
        return state
    
    def _check_break_signal(self, state: Dict[str, Any]) -> bool:
        """
        Check if the _break signal is present in the state.
        
        Args:
            state: Current state dictionary
        
        Returns:
            True if _break is set to True, False otherwise
        """
        return state.get('_break', False) is True
    
    def _inject_iteration_vars(self, state: Dict[str, Any], iteration: int, max_iter: int = None):
        """
        Inject automatic iteration variables into state.
        
        Args:
            state: State dictionary to modify
            iteration: Current iteration number (0-indexed)
            max_iter: Maximum iteration count (optional)
        """
        state['_iter'] = iteration
        if max_iter is not None:
            state['_max_iter'] = max_iter
    
    async def _build_and_run_body(self, runner, rundir, iteration: int = 0) -> TaskDataResult:
        """
        Build the body sub-graph for an iteration and execute it.
        
        This method should be overridden by subclasses to customize how the body is built.
        The default implementation is a placeholder.
        
        Args:
            runner: TaskRunner instance
            rundir: Run directory for execution
            iteration: Current iteration number
        
        Returns:
            TaskDataResult from body execution
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement _build_and_run_body")
    
    async def do_run(self, runner, rundir, memento=None) -> TaskDataResult:
        """
        Execute the control flow construct.
        
        This base implementation should be overridden by specific control flow subclasses.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement do_run")
