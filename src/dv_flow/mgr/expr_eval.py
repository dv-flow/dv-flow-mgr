#****************************************************************************
#* expr_eval.py
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
import dataclasses as dc
import json
import subprocess
import re
import tempfile
import os
from typing import Any, Callable, Dict, List, Optional
from .expr_parser import ExprParser, ExprVisitor, Expr, ExprBin, ExprBinOp
from .expr_parser import ExprCall, ExprHId, ExprId, ExprString, ExprInt, ExprUnary, ExprUnaryOp, ExprBool, ExprVar
from .name_resolution import VarResolver
from .filter_registry import FilterRegistry

@dc.dataclass
class ExprEval(ExprVisitor):
    methods: Dict[str, Callable] = dc.field(default_factory=dict)
    name_resolution: Optional[VarResolver] = None
    variables: Dict[str, object] = dc.field(default_factory=dict)
    value: Any = None
    filter_registry: Optional[FilterRegistry] = None
    current_package: Optional[str] = None

    def __post_init__(self):
        self.methods['shell'] = self._builtin_shell
        # JQ-style builtin methods
        self.methods['length'] = self._builtin_length
        self.methods['keys'] = self._builtin_keys
        self.methods['values'] = self._builtin_values
        self.methods['sort'] = self._builtin_sort
        self.methods['unique'] = self._builtin_unique
        self.methods['reverse'] = self._builtin_reverse
        self.methods['map'] = self._builtin_map
        self.methods['select'] = self._builtin_select
        self.methods['first'] = self._builtin_first
        self.methods['last'] = self._builtin_last
        self.methods['flatten'] = self._builtin_flatten
        self.methods['type'] = self._builtin_type
        self.methods['split'] = self._builtin_split
        self.methods['group_by'] = self._builtin_group_by

    def set(self, name: str, value: object):
        self.variables[name] = value

    def set_name_resolution(self, ctx: VarResolver):
        self.name_resolution = ctx

    def eval(self, expr_s: str) -> str:
        if expr_s is None:
            return None
        elif isinstance(expr_s, Expr):
            expr_s.accept(self)
            return self._toString(self.value)
        elif isinstance(expr_s, bool):
            return expr_s
        else:
            parser = ExprParser()
            ast = parser.parse(expr_s)

            self.value = None
            ast.accept(self)
            val = self._toString(self.value)
            return val
    
    def _toString(self, val):
        rval = val
        if type(val) != str:
            obj = self._toObject(val)
            rval = json.dumps(obj)
        return rval
    
    def _toObject(self, val):
        rval = val
        if isinstance(val, list):
            rval = list(self._toObject(v) for v in val)
        elif hasattr(val, "model_dump"):
            rval = val.model_dump()

        return rval

    def visitExprHId(self, e: ExprHId):
        # Check for default value syntax (e.g., env.CC:-gcc)
        id_parts = e.id.copy()
        default_value = None
        
        # Check if last part contains :-
        if ':-' in id_parts[-1]:
            parts = id_parts[-1].split(':-', 1)
            id_parts[-1] = parts[0]
            default_value = parts[1]
        
        # First try to resolve using name resolution context
        value = None

        if self.name_resolution:
            # Try full qualified name first (e.g. foo.DEBUG)
            fq_name = ".".join(id_parts)
            value = self.name_resolution.resolve_variable(fq_name)
            if value is None:
                # Fallback to first identifier (e.g. package or var)
                value = self.name_resolution.resolve_variable(id_parts[0])

        # Fall back to variables dict
        if value is None and id_parts[0] in self.variables:
            value = self.variables[id_parts[0]]

        if value is None:
            if default_value is not None:
                self.value = default_value
                return
            raise Exception("Variable '%s' not found" % id_parts[0])

        # If qualified lookup returned a terminal value, stop here
        # Otherwise, traverse remaining identifiers
        for i in range(1, len(id_parts)):
            if isinstance(value, dict):
                if id_parts[i] in value.keys():
                    value = value[id_parts[i]]
                else:
                    if default_value is not None:
                        self.value = default_value
                        return
                    raise Exception("Sub-element '%s' not found in '%s'" % (id_parts[i], ".".join(id_parts)))
            elif hasattr(value, id_parts[i]):
                value = getattr(value, id_parts[i])
            else:
                # If value is a primitive (bool/int/str), treat as terminal
                if isinstance(value, (bool, int, float, str)):
                    break
                if default_value is not None:
                    self.value = default_value
                    return
                raise Exception("Sub-element '%s' not found in '%s' (%s)" % (id_parts[i], ".".join(id_parts), value))
        self.value = value

    def visitExprId(self, e: ExprId):
        # Check for default value syntax (e.g., CC:-gcc)
        id_str = e.id
        default_value = None
        
        if ':-' in id_str:
            parts = id_str.split(':-', 1)
            id_str = parts[0]
            default_value = parts[1]
        
        # First try to resolve using name resolution context
        if self.name_resolution:
            resolved = self.name_resolution.resolve_variable(id_str)
            if resolved is not None:
                self.value = resolved
                return

        # Fall back to variables dict
        if id_str in self.variables:
            self.value = self._toObject(self.variables[id_str])
        else:
            if default_value is not None:
                self.value = default_value
            else:
                raise Exception("Variable '%s' not found" % id_str)

    def visitExprString(self, e: ExprString):
        self.value = e.value
    
    def visitExprBin(self, e):
        e.lhs.accept(self)
        lhs_val = self.value
        
        # For pipe operator, RHS should be a filter call
        if e.op == ExprBinOp.Pipe:
            # lhs_val is the input to the filter
            # rhs should be either an ID (filter name), HId (qualified filter name), or Call (filter with params)
            if isinstance(e.rhs, ExprId):
                # Check if it's a builtin method first
                if e.rhs.id in self.methods:
                    # Builtin method: value | method
                    self.value = self.methods[e.rhs.id](lhs_val, [])
                else:
                    # Simple filter: value | filter_name
                    self.value = self._apply_filter(e.rhs.id, lhs_val, {})
            elif isinstance(e.rhs, ExprHId):
                # Qualified filter: value | pkg.filter_name
                filter_name = ".".join(e.rhs.id)
                self.value = self._apply_filter(filter_name, lhs_val, {})
            elif isinstance(e.rhs, ExprCall):
                # Check if it's a builtin method first
                if e.rhs.id in self.methods:
                    # Builtin method: value | method(args)
                    # Evaluate arguments
                    args = []
                    for arg in e.rhs.args:
                        self.value = None
                        arg.accept(self)
                        args.append(self.value)
                    # Call the builtin with lhs as input
                    self.value = self.methods[e.rhs.id](lhs_val, args)
                else:
                    # Filter with params: value | filter_name(arg1, arg2)
                    # Evaluate arguments
                    args = {}
                    for i, arg in enumerate(e.rhs.args):
                        self.value = None
                        arg.accept(self)
                        args[f"arg{i}"] = self.value
                    self.value = self._apply_filter(e.rhs.id, lhs_val, args)
            else:
                # For backward compatibility, evaluate RHS
                e.rhs.accept(self)
                rhs_val = self.value
        else:
            # All other operators need RHS evaluated
            e.rhs.accept(self)
            rhs_val = self.value
            
            if e.op == ExprBinOp.Plus:
                self.value = lhs_val + rhs_val
            elif e.op == ExprBinOp.Minus:
                self.value = lhs_val - rhs_val
            elif e.op == ExprBinOp.Times:
                self.value = lhs_val * rhs_val
            elif e.op == ExprBinOp.Divide:
                self.value = lhs_val / rhs_val
            # Comparison operators
            elif e.op == ExprBinOp.Eq:
                self.value = lhs_val == rhs_val
            elif e.op == ExprBinOp.Ne:
                self.value = lhs_val != rhs_val
            elif e.op == ExprBinOp.Lt:
                self.value = lhs_val < rhs_val
            elif e.op == ExprBinOp.Le:
                self.value = lhs_val <= rhs_val
            elif e.op == ExprBinOp.Gt:
                self.value = lhs_val > rhs_val
            elif e.op == ExprBinOp.Ge:
                self.value = lhs_val >= rhs_val
            # Logical operators
            elif e.op == ExprBinOp.And:
                self.value = self._to_bool(lhs_val) and self._to_bool(rhs_val)
            elif e.op == ExprBinOp.Or:
                self.value = self._to_bool(lhs_val) or self._to_bool(rhs_val)
    
    def visitExprUnary(self, e):
        e.expr.accept(self)
        
        if e.op == ExprUnaryOp.Not:
            self.value = not self._to_bool(self.value)
    
    def _to_bool(self, val):
        """Convert value to boolean using truthiness rules"""
        if val is None or val is False:
            return False
        if val == "" or val == 0 or val == [] or val == {}:
            return False
        return True
    
    def visitExprCall(self, e: ExprCall):
        if e.id in self.methods:
            # Need to gather up argument values
            in_value = self.value
            args = []
            for arg in e.args:
                self.value = None
                arg.accept(self)
                args.append(self.value)

            self.value = self.methods[e.id](in_value, args)
        else:
            raise Exception("Method %s not found" % e.id)
        
    def visitExprInt(self, e: ExprInt):
        self.value = e.value
    
    def visitExprBool(self, e: ExprBool):
        self.value = e.value
    
    def visitExprVar(self, e: ExprVar):
        """Evaluate variable reference: $name"""
        if e.name in self.variables:
            self.value = self.variables[e.name]
        else:
            raise Exception(f"Variable '${e.name}' not found")
    
    def visitExprIndex(self, e):
        """Evaluate array/object indexing: obj[index] or obj[start:end]"""
        # Evaluate the object
        e.obj.accept(self)
        obj = self.value
        
        if e.is_slice:
            # Handle slice: obj[start:end]
            start = None
            end = None
            
            if e.start:
                e.start.accept(self)
                start = self.value
            
            if e.end:
                e.end.accept(self)
                end = self.value
            
            # Python slice
            try:
                self.value = obj[start:end]
            except (TypeError, KeyError, IndexError) as ex:
                raise Exception(f"Cannot slice {type(obj).__name__}: {ex}")
        else:
            # Handle single index: obj[index]
            e.index.accept(self)
            index = self.value
            
            try:
                if isinstance(obj, dict):
                    # Dictionary access
                    self.value = obj.get(index)
                elif isinstance(obj, (list, tuple, str)):
                    # Array/string access
                    self.value = obj[index]
                else:
                    raise Exception(f"Cannot index {type(obj).__name__}")
            except (KeyError, IndexError) as ex:
                raise Exception(f"Index {index} not found in {type(obj).__name__}: {ex}")
    
    def visitExprIterator(self, e):
        """Evaluate array iterator: obj[] - returns all elements"""
        e.obj.accept(self)
        obj = self.value
        
        if isinstance(obj, list):
            # For arrays, return the list itself (jq .[] iterates, but we return the data)
            self.value = obj
        elif isinstance(obj, dict):
            # For objects, return values
            self.value = list(obj.values())
        else:
            raise Exception(f"Cannot iterate over {type(obj).__name__}")

    def _builtin_shell(self, in_value, args):
        """Execute shell command and return stdout"""
        if len(args) != 1:
            raise Exception("shell() requires exactly one argument")
        
        command = str(args[0])
        
        # Expand nested expressions in command string
        command = self._expand_nested_expressions(command)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_msg = f"shell() command failed: {command}\n"
            if e.stdout:
                error_msg += f"stdout: {e.stdout}\n"
            if e.stderr:
                error_msg += f"stderr: {e.stderr}"
            raise Exception(error_msg)

    def _expand_nested_expressions(self, text: str) -> str:
        """Recursively expand ${{ ... }} expressions in text"""
        pattern = r'\$\{\{\s*(.*?)\s*\}\}'
        
        def replace_expr(match):
            expr_content = match.group(1)
            # Recursively evaluate the expression
            return self.eval(expr_content)
        
        # Keep replacing until no more expressions found
        prev_text = None
        while prev_text != text:
            prev_text = text
            text = re.sub(pattern, replace_expr, text)
        
        return text

    def _apply_filter(self, filter_name: str, input_data: Any, params: Dict[str, Any]) -> Any:
        """Apply a filter to input data with parameters"""
        if self.filter_registry is None:
            raise Exception(f"Filter '{filter_name}' used but no filter registry configured")
        
        if self.current_package is None:
            raise Exception(f"Filter '{filter_name}' used but current package not set")
        
        # Resolve the filter
        filter_def = self.filter_registry.resolve_filter(self.current_package, filter_name)
        if filter_def is None:
            raise Exception(f"Filter '{filter_name}' not found in package '{self.current_package}'")
        
        # Execute based on implementation type
        if filter_def.expr is not None:
            return self._eval_jq_filter(filter_def, input_data, params)
        elif filter_def.run is not None:
            if filter_def.shell == "python3" or filter_def.shell == "python":
                return self._eval_python_filter(filter_def, input_data, params)
            else:
                return self._eval_shell_filter(filter_def, input_data, params)
        else:
            raise Exception(f"Filter '{filter_name}' has no implementation")
    
    def _eval_jq_filter(self, filter_def, input_data: Any, params: Dict[str, Any]) -> Any:
        """Evaluate a jq expression filter"""
        # For now, just evaluate the expression directly
        # TODO: Implement native jq operators (Phase 3)
        
        # Create a new eval context with filter parameters and input
        filter_eval = ExprEval(
            methods=self.methods.copy(),
            name_resolution=self.name_resolution,
            variables=self.variables.copy(),
            filter_registry=self.filter_registry,
            current_package=self.current_package
        )
        
        # Set filter parameters
        for param_name, param_value in params.items():
            filter_eval.set(param_name, param_value)
        
        # Set special input variable
        filter_eval.set("input", input_data)
        
        # Evaluate the expression
        result = filter_eval.eval(filter_def.expr)
        
        # Try to parse as JSON if it's a string
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        return result
    
    def _eval_python_filter(self, filter_def, input_data: Any, params: Dict[str, Any]) -> Any:
        """Evaluate a Python script filter"""
        # Prepare the script
        script = filter_def.run
        
        # Create globals with standard library
        filter_globals = {
            '__builtins__': __builtins__,
            'json': json,
            're': re,
        }
        
        # Execute the script to define the filter function
        try:
            exec(script, filter_globals)
        except Exception as e:
            raise Exception(f"Python filter '{filter_def.name}' failed to compile: {e}")
        
        # Check for filter function
        if 'filter' not in filter_globals:
            raise Exception(f"Python filter '{filter_def.name}' must define a 'filter' function")
        
        filter_func = filter_globals['filter']
        
        # Call the filter function
        try:
            result = filter_func(input_data, **params)
            return result
        except Exception as e:
            raise Exception(f"Python filter '{filter_def.name}' execution failed: {e}")
    
    def _eval_shell_filter(self, filter_def, input_data: Any, params: Dict[str, Any]) -> Any:
        """Evaluate a shell script filter"""
        # Create environment with parameters
        env = os.environ.copy()
        
        # Add filter parameters as environment variables
        for param_name, param_value in params.items():
            env[param_name.upper()] = str(param_value)
        
        # Prepare input as JSON string
        if isinstance(input_data, str):
            input_json = input_data
        else:
            input_json = json.dumps(input_data)
        
        # Create a temporary script file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(filter_def.run)
            script_path = f.name
        
        try:
            # Execute the shell script
            result = subprocess.run(
                [filter_def.shell, script_path],
                input=input_json,
                capture_output=True,
                text=True,
                env=env,
                timeout=10  # 10 second timeout
            )
            
            if result.returncode != 0:
                raise Exception(f"Shell filter '{filter_def.name}' failed with exit code {result.returncode}: {result.stderr}")
            
            output = result.stdout.strip()
            
            # Try to parse as JSON
            try:
                return json.loads(output)
            except (json.JSONDecodeError, TypeError):
                return output
        
        except subprocess.TimeoutExpired:
            raise Exception(f"Shell filter '{filter_def.name}' timed out after 10 seconds")
        except Exception as e:
            raise Exception(f"Shell filter '{filter_def.name}' execution failed: {e}")
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except:
                pass
    
    # ========== JQ-style Builtin Methods ==========
    
    def _builtin_length(self, in_value, args):
        """length() - Get length of array/object/string"""
        # When called as length(arr), arr is passed as arg
        # When called as arr | length, arr is in in_value
        if len(args) == 1:
            target = args[0]
        elif len(args) == 0:
            target = in_value
        else:
            raise Exception("length() takes at most one argument")
        
        if isinstance(target, (list, dict, str)):
            return len(target)
        elif target is None:
            return 0
        else:
            raise Exception(f"length() cannot be applied to {type(target).__name__}")
    
    def _builtin_keys(self, in_value, args):
        """keys() - Get sorted keys of object or indices of array"""
        if len(args) > 0:
            raise Exception("keys() takes no arguments")
        
        if isinstance(in_value, dict):
            return sorted(in_value.keys())
        elif isinstance(in_value, list):
            return list(range(len(in_value)))
        else:
            raise Exception(f"keys() cannot be applied to {type(in_value).__name__}")
    
    def _builtin_values(self, in_value, args):
        """values() - Get values of object"""
        if len(args) > 0:
            raise Exception("values() takes no arguments")
        
        if isinstance(in_value, dict):
            return list(in_value.values())
        elif isinstance(in_value, list):
            return in_value
        else:
            raise Exception(f"values() cannot be applied to {type(in_value).__name__}")
    
    def _builtin_sort(self, in_value, args):
        """sort() - Sort array"""
        if len(args) > 0:
            raise Exception("sort() takes no arguments")
        
        if isinstance(in_value, list):
            try:
                return sorted(in_value)
            except TypeError as e:
                raise Exception(f"sort() failed: items are not comparable ({e})")
        else:
            raise Exception(f"sort() requires array input, got {type(in_value).__name__}")
    
    def _builtin_unique(self, in_value, args):
        """unique() - Get unique elements from array"""
        if len(args) > 0:
            raise Exception("unique() takes no arguments")
        
        if isinstance(in_value, list):
            seen = set()
            result = []
            for item in in_value:
                try:
                    # Try hashable types
                    if item not in seen:
                        seen.add(item)
                        result.append(item)
                except TypeError:
                    # Unhashable type, do linear search
                    if item not in result:
                        result.append(item)
            return result
        else:
            raise Exception(f"unique() requires array input, got {type(in_value).__name__}")
    
    def _builtin_reverse(self, in_value, args):
        """reverse() - Reverse array or string"""
        if len(args) > 0:
            raise Exception("reverse() takes no arguments")
        
        if isinstance(in_value, list):
            return list(reversed(in_value))
        elif isinstance(in_value, str):
            return in_value[::-1]
        else:
            raise Exception(f"reverse() requires array or string input, got {type(in_value).__name__}")
    
    def _builtin_map(self, in_value, args):
        """map(expr) - Transform each element of array"""
        if len(args) != 1:
            raise Exception("map() requires exactly one argument (expression)")
        
        if not isinstance(in_value, list):
            raise Exception(f"map() requires array input, got {type(in_value).__name__}")
        
        # The argument is an expression AST node - we need to evaluate it for each element
        # For now, we'll handle this as a string expression
        expr_str = str(args[0])
        
        result = []
        for item in in_value:
            # Create temporary evaluator with item as context
            temp_eval = ExprEval(
                methods=self.methods.copy(),
                name_resolution=self.name_resolution,
                variables=self.variables.copy(),
                filter_registry=self.filter_registry,
                current_package=self.current_package
            )
            temp_eval.set("item", item)
            temp_eval.value = item  # Set as current value
            
            # Evaluate expression for this item
            result.append(temp_eval.eval(expr_str))
        
        return result
    
    def _builtin_select(self, in_value, args):
        """select(condition) - Filter elements by condition"""
        if len(args) != 1:
            raise Exception("select() requires exactly one argument (condition)")
        
        # Evaluate condition with input as context
        condition_str = str(args[0])
        
        temp_eval = ExprEval(
            methods=self.methods.copy(),
            name_resolution=self.name_resolution,
            variables=self.variables.copy(),
            filter_registry=self.filter_registry,
            current_package=self.current_package
        )
        temp_eval.value = in_value
        temp_eval.set("item", in_value)
        
        result = temp_eval.eval(condition_str)
        
        # Return input if condition is true, None otherwise
        return in_value if self._to_bool(result) else None
    
    def _builtin_first(self, in_value, args):
        """first() - Get first element of array"""
        if len(args) > 0:
            raise Exception("first() takes no arguments")
        
        if isinstance(in_value, list):
            return in_value[0] if len(in_value) > 0 else None
        else:
            raise Exception(f"first() requires array input, got {type(in_value).__name__}")
    
    def _builtin_last(self, in_value, args):
        """last() - Get last element of array"""
        if len(args) > 0:
            raise Exception("last() takes no arguments")
        
        if isinstance(in_value, list):
            return in_value[-1] if len(in_value) > 0 else None
        else:
            raise Exception(f"last() requires array input, got {type(in_value).__name__}")
    
    def _builtin_flatten(self, in_value, args):
        """flatten([depth]) - Flatten nested arrays"""
        depth = 1  # Default depth
        if len(args) > 1:
            raise Exception("flatten() takes at most one argument (depth)")
        elif len(args) == 1:
            depth = int(args[0])
        
        if not isinstance(in_value, list):
            raise Exception(f"flatten() requires array input, got {type(in_value).__name__}")
        
        def _flatten_recursive(lst, d):
            if d <= 0:
                return lst
            result = []
            for item in lst:
                if isinstance(item, list):
                    result.extend(_flatten_recursive(item, d - 1))
                else:
                    result.append(item)
            return result
        
        return _flatten_recursive(in_value, depth)
    
    def _builtin_type(self, in_value, args):
        """type() - Get type of value"""
        if len(args) > 0:
            raise Exception("type() takes no arguments")
        
        if in_value is None:
            return "null"
        elif isinstance(in_value, bool):
            return "boolean"
        elif isinstance(in_value, int):
            return "number"
        elif isinstance(in_value, float):
            return "number"
        elif isinstance(in_value, str):
            return "string"
        elif isinstance(in_value, list):
            return "array"
        elif isinstance(in_value, dict):
            return "object"
        else:
            return "unknown"
    
    def _builtin_split(self, in_value, args):
        """split(sep) - Split string by separator"""
        if len(args) != 1:
            raise Exception("split() requires exactly one argument (separator)")
        
        if not isinstance(in_value, str):
            raise Exception(f"split() can only be applied to strings, not {type(in_value).__name__}")
        
        separator = args[0]
        if not isinstance(separator, str):
            raise Exception(f"split() separator must be a string, not {type(separator).__name__}")
        
        return in_value.split(separator)
    
    def _builtin_group_by(self, in_value, args):
        """group_by(expr) - Group array elements by expression result"""
        if len(args) != 1:
            raise Exception("group_by() requires exactly one argument (expression)")
        
        if not isinstance(in_value, list):
            raise Exception(f"group_by() can only be applied to arrays, not {type(in_value).__name__}")
        
        expr = args[0]
        
        # Group items by the expression result
        from collections import defaultdict
        groups = defaultdict(list)
        
        for item in in_value:
            # Create a temporary evaluator for this item
            temp_eval = ExprEval(
                methods=self.methods.copy(),
                name_resolution=self.name_resolution,
                variables=self.variables.copy(),
                filter_registry=self.filter_registry,
                current_package=self.current_package
            )
            temp_eval.set("input", item)
            
            # Evaluate the expression
            expr.accept(temp_eval)
            key = temp_eval.value
            
            # Convert unhashable types to strings for grouping
            if isinstance(key, (list, dict)):
                key = json.dumps(key, sort_keys=True)
            
            groups[key].append(item)
        
        # Return list of groups
        return list(groups.values())
