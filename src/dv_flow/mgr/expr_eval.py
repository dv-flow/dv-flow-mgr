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
        # First try to resolve using name resolution context
        value = None

        if self.name_resolution:
            value = self.name_resolution.resolve_variable(e.id[0])

        # Fall back to variables dict
        if value is None and e.id[0] in self.variables:
            value = self.variables[e.id[0]]

        if value is None:
            raise Exception("Variable '%s' not found" % e.id[0])

        for i in range(1, len(e.id)):
            if isinstance(value, dict):
                if e.id[i] in value.keys():
                    value = value[e.id[i]]
                else:
                    raise Exception("Sub-element '%s' not found in '%s'" % (e.id[i], ".".join(e.id)))
            elif hasattr(value, e.id[i]):
                value = getattr(value, e.id[i])
            else:
                raise Exception("Sub-element '%s' not found in '%s' (%s)" % (e.id[i], ".".join(e.id), value))
        self.value = value

    def visitExprId(self, e: ExprId):
        # First try to resolve using name resolution context
        if self.name_resolution:
            resolved = self.name_resolution.resolve_variable(e.id)
            if resolved is not None:
                self.value = resolved
                return

        # Fall back to variables dict
        if e.id in self.variables:
            self.value = self._toObject(self.variables[e.id])
        else:
            raise Exception("Variable '%s' not found" % e.id)

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
