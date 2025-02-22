import pytest
from dv_flow.mgr.expr_parser import ExprParser, ExprVisitor2String


def test_smoke():
#    content = "in | jq('.[] | select(.name == \"foo\")') | out"
    content = "in | jq(\".[] | select()\") | out(a, b) | out()"

    parser = ExprParser()
    expr = parser.parse(content)
    print("Expr: %s" % ExprVisitor2String.toString(expr))

    expr = parser.parse(content)
    print("Expr: %s" % ExprVisitor2String.toString(expr))


