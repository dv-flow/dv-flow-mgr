
import dataclasses as dc
import json
from typing import Any, Callable, Dict, List
from .expr_parser import ExprVisitor, Expr, ExprBin, ExprBinOp, ExprCall, ExprId, ExprString, ExprInt

@dc.dataclass
class ExprEval(ExprVisitor):
    methods : Dict[str, Callable] = dc.field(default_factory=dict)
    variables : Dict[str, object] = dc.field(default_factory=dict)
    value : Any = None

    def eval(self, e : Expr) -> str:
        self.value = None
        e.accept(self)

        val = self._toString(self.value)

        return val
    
    def _toString(self, val):
        rval = val
        if type(val) != str:
            obj = self._toObject(val)
            rval = json.dumps(obj)
        return rval
#        if isinstance(val, list):
#            val = '[' + ",".join(self._toString(v) for v in val) + ']'
#        elif hasattr(val, "model_dump_json"):
#            val = val.model_dump_json()
#        return val
    
    def _toObject(self, val):
        rval = val
        if isinstance(val, list):
            rval = list(self._toObject(v) for v in val)
        elif hasattr(val, "model_dump"):
            rval = val.model_dump()

        return rval

    def visitExprId(self, e : ExprId):
        if e.id in self.variables:
            # Always represent data as a JSON object
            self.value = self._toObject(self.variables[e.id])
        else:
            raise Exception("Variable '%s' not found" % e.id)

    def visitExprString(self, e : ExprString):
        self.value = e.value
    
    def visitExprBin(self, e):
        e.lhs.accept(self)

        if e.op == ExprBinOp.Pipe:
            # Value just goes over to the rhs
            e.rhs.accept(self)
        elif e.op == ExprBinOp.Plus:
            pass
    
    def visitExprCall(self, e : ExprCall):
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
        
    def visitExprInt(self, e : ExprInt):
        self.value = e.value
