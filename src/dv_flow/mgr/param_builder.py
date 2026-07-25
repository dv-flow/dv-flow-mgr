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
from .param_types import (TypeKind, ParamTypeError, normalize_type,
                          coerce_to_kind, check_value_set)
from .expr_eval import ResolveError
from .task import iter_uses_chain

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
        
        # Step 2b: Value sets inherit independently of values (see
        # task.collect_param_value_sets), so they are collected from the chain
        # rather than read off the winning ParamDef.
        value_sets = self._collect_value_sets(param_chain)

        # Step 3: Evaluate template expressions in order
        evaluated_params = self._evaluate_params(
            merged_defs, task.name, task, value_sets)
        
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

        for current in iter_uses_chain(task):
            if hasattr(current, 'param_defs') and current.param_defs:
                self._log.debug(f"  Adding param_defs from {current.name}: {len(current.param_defs.definitions)} params")
                chain.append(current.param_defs)
            elif hasattr(current, 'paramT') and current.paramT:
                # Base task/type uses old-style paramT, convert it to ParamDefCollection
                self._log.debug(f"  Converting paramT to param_defs for {current.name}")
                param_defs = self._paramT_to_param_defs(current.paramT, current.name)
                chain.append(param_defs)

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
                    # Parameter override - keep existing type if not specified
                    existing_def, existing_type = merged[name]
                    new_type = collection.types.get(name) or existing_type
                    if param_def.has_list_op():
                        # Resolve append/prepend against existing base value
                        resolved_value = param_def.resolve_value(existing_def.value)
                        merged[name] = (ParamDef(value=resolved_value), new_type)
                        self._log.debug(f"  Append/prepend param {name}: type={new_type}, value={resolved_value}")
                    else:
                        merged[name] = (param_def, new_type)
                        self._log.debug(f"  Overriding param {name}: type={new_type}, value={param_def.value}")
        
        return merged
    
    def _collect_value_sets(self, chain: List[ParamDefCollection]) -> Dict[str, Any]:
        """{param: ValueSet} from the inheritance chain, nearest winning.

        `chain` is derived-first, so walking it in reverse lets a derived
        declaration replace the inherited set while a declaration that is silent
        about `values:` keeps it.
        """
        sets = {}
        for collection in reversed(chain):
            for name, param_def in collection.definitions.items():
                vs = getattr(param_def, 'values', None)
                if vs is not None:
                    sets[name] = vs
        return sets

    def _uses_chain_pkg_names(self, task: 'Task') -> List[str]:
        """Ordered, de-duplicated package names along the task's `uses` chain
        (most-derived first — e.g. [foo, hdlsim]). This is the same chain that
        binds elaborators and assembles paramT; resolve()'s package fall-through
        walks it (see docs/proposals/task_elaboration_impl_plan.md §B.3)."""
        names = []
        seen = set()
        for current in iter_uses_chain(task):
            pkg = getattr(current, 'package', None)
            pname = getattr(pkg, 'name', None) if pkg is not None else None
            if pname is not None and pname not in seen:
                seen.add(pname)
                names.append(pname)
        return names

    def _evaluate_params(self, merged_defs: Dict[str, Tuple[ParamDef, type]], task_name: str, task: 'Task' = None, value_sets: Dict[str, Any] = None) -> Dict[str, Tuple[type, Any]]:
        """
        Evaluate parameter values in definition order.
        As each parameter is evaluated, add it to eval context for subsequent refs.
        Returns: {param_name: (type, evaluated_value)}
        """
        evaluated = {}

        # Save current eval state to restore later
        saved_vars = self.eval.expr_eval.variables.copy()

        # Expose the instance task's `uses`-chain package names so resolve() can
        # fall through to package-level variables (Feature B). Reset in finally.
        self.eval.expr_eval.uses_chain_pkgs = \
            self._uses_chain_pkg_names(task) if task is not None else None

        try:
            # Process parameters in order they appear (dict maintains insertion order in Python 3.7+)
            for name, (param_def, ptype) in merged_defs.items():
                value = param_def.value

                # Expose the parameter name so the implicit-name forms of
                # resolve() (resolve() / resolve(default)) know which parameter
                # they are defining.
                self.eval.expr_eval.current_param_name = name

                # Evaluate template expressions
                if isinstance(value, str) and "${{" in value:
                    try:
                        value = self.eval.eval(value)
                        self._log.debug(f"  Evaluated param {name}: {param_def.value} -> {value}")
                    except ResolveError as e:
                        # Scoped-variable errors are real errors: a misused or
                        # unresolvable resolve() must surface, not silently leave
                        # the literal "${{ resolve(...) }}" string in place.
                        raise ParamTypeError(
                            "task '%s' parameter '%s': %s" % (task_name, name, e),
                            getattr(e, "srcinfo", None))
                    except Exception as e:
                        self._log.debug(f"  Failed to evaluate param {name}: {e}")
                        # Keep original value on error
                elif isinstance(value, list):
                    new_list = []
                    for v in value:
                        if isinstance(v, str) and "${{" in v:
                            try:
                                ev = self.eval.eval(v)
                            except ResolveError as e:
                                raise ParamTypeError(
                                    "task '%s' parameter '%s': %s" % (task_name, name, e),
                                    getattr(e, "srcinfo", None))
                            except:
                                ev = v
                            # A whole-value ref that resolves to a list is
                            # SPLICED into the parent list (typed-param
                            # expansion) rather than nested as one element. This
                            # is what makes list-op composition flat, e.g.
                            # `plusargs: { prepend: "${{ lead }}", value:
                            # "${{ plusargs }}" }` -> [lead..., plusargs...]
                            # instead of [[lead...], [plusargs...]].
                            if isinstance(ev, list):
                                new_list.extend(ev)
                            else:
                                new_list.append(ev)
                        else:
                            new_list.append(v)
                    value = new_list
                elif isinstance(value, dict):
                    new_dict = {}
                    for k, v in value.items():
                        if isinstance(v, str) and "${{" in v:
                            try:
                                new_dict[k] = self.eval.eval(v)
                            except ResolveError as e:
                                raise ParamTypeError(
                                    "task '%s' parameter '%s': %s" % (task_name, name, e),
                                    getattr(e, "srcinfo", None))
                            except:
                                new_dict[k] = v
                        else:
                            new_dict[k] = v
                    value = new_dict
                
                # Coerce the evaluated value to the destination kind before it
                # is modeled/validated. Only LIST/MAP/STR do real work; scalar
                # kinds and ANY pass through (pydantic still validates scalars).
                # This is where a whole-value list ref keeps its list type and a
                # scalar into a list slot is wrapped. See proposal §5.2/§5.3.
                kind = normalize_type(ptype)
                if kind is not TypeKind.ANY:
                    try:
                        value = coerce_to_kind(value, kind)
                    except ParamTypeError as e:
                        raise ParamTypeError(
                            "task '%s' parameter '%s': %s" % (
                                task_name, name, e), getattr(e, "srcinfo", None))

                # Value set, checked AFTER coercion so it always sees the final
                # typed value. This covers both the declaration's own default
                # and any `uses:`/`with:` override layered onto it.
                vs = (value_sets or {}).get(name)
                if vs is not None:
                    warning = check_value_set(
                        value, vs, kind,
                        name="task '%s' parameter '%s'" % (task_name, name),
                        srcinfo=getattr(param_def, "srcinfo", None))
                    if warning is not None:
                        self._log.warning(warning)

                # Store evaluated value
                evaluated[name] = (ptype, value)

                # Update eval context so subsequent params can reference this value
                self.eval.set(name, value)
        finally:
            # Restore eval state
            self.eval.expr_eval.variables = saved_vars
            self.eval.expr_eval.current_param_name = None
            self.eval.expr_eval.uses_chain_pkgs = None

        return evaluated
    
    def _create_pydantic_model(self, task_name: str, evaluated_params: Dict[str, Tuple[type, Any]]) -> type:
        """Create Pydantic model from evaluated parameters"""
        field_dict = {}
        for name, (ptype, value) in evaluated_params.items():
            # ANY floor: a declared param whose destination type couldn't be
            # resolved (e.g. an override across a compound/paramT seam) arrives
            # here with ptype=None. Emitting (None, value) types the pydantic
            # field as NoneType, which rejects every value ("Expected none").
            # Degrade unresolved types to typing.Any (permissive passthrough)
            # so a carried list/map override validates instead of crashing.
            # See docs/proposals/typed_param_expansion.md §5.1.
            if ptype is None:
                ptype = Any
            field_dict[name] = (ptype, value)
        
        # Clean task name for model name (replace dots with underscores)
        clean_name = task_name.replace(".", "_").replace("-", "_")
        model_name = f"Task{clean_name}Params"
        
        self._log.debug(f"Creating Pydantic model {model_name} with {len(field_dict)} fields")
        return pydantic.create_model(model_name, **field_dict)
