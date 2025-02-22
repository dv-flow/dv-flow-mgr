
import dataclasses as dc
from typing import Any, Callable, Dict, List
from .expr_parser import ExprVisitor, Expr, ExprBin, ExprBinOp, ExprCall, ExprId, ExprString, ExprInt

@dc.dataclass
class ExprEval(ExprVisitor):
    methods : Dict[str, Callable] = dc.field(default_factory=dict)
    variables : Dict[str, object] = dc.field(default_factory=dict)
    value : Any = None

    def eval(self, e : Expr):
        self.value = None
        e.accept(self)
        return self.value

    def visitExprId(self, e : ExprId):
        if e.id in self.variables:
            self.value = self.variables[e.id]
        else:
            raise Exception("Variable %s not found" % e.id)

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
