#****************************************************************************
#* param_builder.py
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
import pydantic
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING
from .param_def import ParamDef
from .param_def_collection import ParamDefCollection

if TYPE_CHECKING:
    from .task import Task
    from .param_ref_eval import ParamRefEval

class ParamBuilder:
    """
    Builds paramT during task graph construction by:
    1. Walking inheritance chain
    2. Merging parameter definitions (child wins)
    3. Evaluating template expressions with full context
    """
    
    def __init__(self, eval_context: 'ParamRefEval'):
        self.eval = eval_context
        self._log = logging.getLogger("ParamBuilder")
    
    def build_param_type(self, task: 'Task') -> type:
        """
        Build paramT for a task by walking inheritance chain.
        Returns a Pydantic model with evaluated parameter values.
        """
        self._log.debug(f"--> build_param_type {task.name}")
        
        # Step 1: Collect parameter definitions from inheritance chain
        param_chain = self._collect_param_chain(task)
        
        # Step 2: Merge definitions (first wins - child overrides parent)
        merged_defs = self._merge_param_defs(param_chain)
        
        # Step 3: Evaluate template expressions in order
        evaluated_params = self._evaluate_params(merged_defs, task.name)
        
        # Step 4: Create Pydantic model
        result = self._create_pydantic_model(task.name, evaluated_params)
        
        self._log.debug(f"<-- build_param_type {task.name}")
        return result
    
    def _collect_param_chain(self, task: 'Task') -> List[ParamDefCollection]:
        """
        Walk the inheritance chain and collect param definitions.
        Returns list in order: [DerivedTask, BaseTask, ..., RootTask]
        """
        chain = []
        current = task
        visited = set()
        
        while current is not None:
            # Prevent infinite loops
            if id(current) in visited:
                self._log.warning(f"Circular inheritance detected for task {task.name}")
                break
            visited.add(id(current))
            
            if hasattr(current, 'param_defs') and current.param_defs:
                self._log.debug(f"  Adding param_defs from {current.name}: {len(current.param_defs.definitions)} params")
                chain.append(current.param_defs)
            elif hasattr(current, 'paramT') and current.paramT:
                # Base task/type uses old-style paramT, convert it to ParamDefCollection
                self._log.debug(f"  Converting paramT to param_defs for {current.name}")
                param_defs = self._paramT_to_param_defs(current.paramT, current.name)
                chain.append(param_defs)
            
            # Move to next in chain
            current = getattr(current, 'uses', None)
        
        self._log.debug(f"Collected {len(chain)} param collections from inheritance chain")
        return chain
    
    def _paramT_to_param_defs(self, paramT: type, task_name: str) -> ParamDefCollection:
        """
        Convert a Pydantic paramT model to ParamDefCollection.
        This handles base tasks that still use eager paramT evaluation.
        """
        from .param_def_collection import ParamDefCollection
        from .param_def import ParamDef
        
        collection = ParamDefCollection()
        
        if hasattr(paramT, 'model_fields'):
            # Create an instance to get default values
            instance = paramT()
            for name, field_info in paramT.model_fields.items():
                value = getattr(instance, name)
                ptype = field_info.annotation
                collection.add_param(name, ParamDef(value=value), ptype)
                self._log.debug(f"    Converted param {name}: type={ptype}, value={value}")
        
        return collection
    
    def _merge_param_defs(self, chain: List[ParamDefCollection]) -> Dict[str, Tuple[ParamDef, type]]:
        """
        Merge parameter definitions with child winning over parent.
        Returns: {param_name: (ParamDef, type)}
        """
        merged = {}
        
        # Process in reverse order (parent first) so child overwrites
        for collection in reversed(chain):
            for name, param_def in collection.definitions.items():
                if name not in merged:
                    # New parameter - add with its type
                    ptype = collection.types.get(name)
                    merged[name] = (param_def, ptype)
                    self._log.debug(f"  Adding param {name}: type={ptype}, value={param_def.value}")
                else:
                    # Parameter override - keep existing type if not specified, update value
                    existing_def, existing_type = merged[name]
                    new_type = collection.types.get(name) or existing_type
                    merged[name] = (param_def, new_type)
                    self._log.debug(f"  Overriding param {name}: type={new_type}, value={param_def.value}")
        
        return merged
    
    def _evaluate_params(self, merged_defs: Dict[str, Tuple[ParamDef, type]], task_name: str) -> Dict[str, Tuple[type, Any]]:
        """
        Evaluate parameter values in definition order.
        As each parameter is evaluated, add it to eval context for subsequent refs.
        Returns: {param_name: (type, evaluated_value)}
        """
        evaluated = {}
        
        # Save current eval state to restore later
        saved_vars = self.eval.expr_eval.variables.copy()
        
        try:
            # Process parameters in order they appear (dict maintains insertion order in Python 3.7+)
            for name, (param_def, ptype) in merged_defs.items():
                value = param_def.value
                
                # Evaluate template expressions
                if isinstance(value, str) and "${{" in value:
                    try:
                        value = self.eval.eval(value)
                        self._log.debug(f"  Evaluated param {name}: {param_def.value} -> {value}")
                    except Exception as e:
                        self._log.debug(f"  Failed to evaluate param {name}: {e}")
                        # Keep original value on error
                elif isinstance(value, list):
                    new_list = []
                    for v in value:
                        if isinstance(v, str) and "${{" in v:
                            try:
                                new_list.append(self.eval.eval(v))
                            except:
                                new_list.append(v)
                        else:
                            new_list.append(v)
                    value = new_list
                elif isinstance(value, dict):
                    new_dict = {}
                    for k, v in value.items():
                        if isinstance(v, str) and "${{" in v:
                            try:
                                new_dict[k] = self.eval.eval(v)
                            except:
                                new_dict[k] = v
                        else:
                            new_dict[k] = v
                    value = new_dict
                
                # Store evaluated value
                evaluated[name] = (ptype, value)
                
                # Update eval context so subsequent params can reference this value
                self.eval.set(name, value)
        finally:
            # Restore eval state
            self.eval.expr_eval.variables = saved_vars
        
        return evaluated
    
    def _create_pydantic_model(self, task_name: str, evaluated_params: Dict[str, Tuple[type, Any]]) -> type:
        """Create Pydantic model from evaluated parameters"""
        field_dict = {}
        for name, (ptype, value) in evaluated_params.items():
            field_dict[name] = (ptype, value)
        
        # Clean task name for model name (replace dots with underscores)
        clean_name = task_name.replace(".", "_").replace("-", "_")
        model_name = f"Task{clean_name}Params"
        
        self._log.debug(f"Creating Pydantic model {model_name} with {len(field_dict)} fields")
        return pydantic.create_model(model_name, **field_dict)
