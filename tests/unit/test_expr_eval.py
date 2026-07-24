
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

    assert result == '10'

def test_hier_path_dict():
    content = "env.HOME"

    env = {
        "HOME": "/home/user"
    }
    
    eval = ExprEval()
    eval.variables["env"] = env

    parser = ExprParser()
    expr = parser.parse(content)
    result = eval.eval(expr)

    assert result == '/home/user'

def test_hier_path_obj():
    content = "env.HOME"

    class env(object):
        HOME : str = "/home/user"
    
    eval = ExprEval()
    eval.variables["env"] = env()

    parser = ExprParser()
    expr = parser.parse(content)
    result = eval.eval(expr)

    assert result == '/home/user'

def test_hier_path_dict_obj():
    content = "env.HOME.foo"

    class bar(object):
        foo : str = "/home/user"

    env = {
        "HOME": bar()
    }
    
    eval = ExprEval()
    eval.variables["env"] = env

    parser = ExprParser()
    expr = parser.parse(content)
    result = eval.eval(expr)

    assert result == '/home/user'

def test_hier_path_obj_obj():
    content = "env.HOME.foo"

    class bar(object):
        foo : str = "/home/user"

    class env(object):
        HOME : object = bar()
    
    eval = ExprEval()
    eval.variables["env"] = env()

    parser = ExprParser()
    expr = parser.parse(content)
    result = eval.eval(expr)

    assert result == '/home/user'
def test_resolve_builtin_dispatch():
    # resolve is registered and both single-arg (implicit name) and two-arg
    # (explicit name) dispatch work.
    eval = ExprEval()
    assert 'resolve' in eval.methods

    eval.current_param_name = 'sim'
    eval.variables['__let__'] = {'sim': 'mti'}

    # single-arg: implicit name 'sim' -> scoped binding wins
    assert eval.eval(ExprParser().parse("resolve('vlt')")) == 'mti'
    # two-arg: explicit name, no binding -> default
    assert eval.eval(ExprParser().parse("resolve('other', 'dflt')")) == 'dflt'
