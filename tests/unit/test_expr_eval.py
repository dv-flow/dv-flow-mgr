
import pytest
from dv_flow.mgr.expr_parser import ExprParser, ExprVisitor2String
from dv_flow.mgr.expr_eval import ExprEval

def test_smoke():
    content = "sum(1, 2, 3, 4)"

    def sum(in_value, args):
        ret = 0
        for arg in args:
            ret += int(arg)
        return ret
    
    eval = ExprEval()
    eval.methods["sum"] = sum

    parser = ExprParser()
    expr = parser.parse(content)
    result = eval.eval(expr)

    assert result == 10



