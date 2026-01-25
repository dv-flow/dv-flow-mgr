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
from typing import Any, Callable, Dict, List, Optional
from .expr_parser import ExprParser, ExprVisitor, Expr, ExprBin, ExprBinOp
from .expr_parser import ExprCall, ExprHId, ExprId, ExprString, ExprInt
from .name_resolution import VarResolver

@dc.dataclass
class ExprEval(ExprVisitor):
    methods: Dict[str, Callable] = dc.field(default_factory=dict)
    name_resolution: Optional[VarResolver] = None
    variables: Dict[str, object] = dc.field(default_factory=dict)
    value: Any = None

    def __post_init__(self):
        self.methods['shell'] = self._builtin_shell

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

        if e.op == ExprBinOp.Pipe:
            # Value just goes over to the rhs
            e.rhs.accept(self)
        elif e.op == ExprBinOp.Plus:
            pass
    
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
