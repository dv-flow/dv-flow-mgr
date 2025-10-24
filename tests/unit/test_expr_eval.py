
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

def test_bool_param_representation():
    """Test that bool parameters use Python string representation (True/False)."""
    eval = ExprEval()
    eval.set('enabled', True)
    eval.set('disabled', False)
    
    # When evaluating bool variables, they should be converted to Python's
    # string representation (True/False), not JSON's representation (true/false)
    result_true = eval.eval('enabled')
    assert result_true == 'True', f"Expected 'True', got '{result_true}'"
    
    result_false = eval.eval('disabled')
    assert result_false == 'False', f"Expected 'False', got '{result_false}'"
    
    # When passing bools directly, they should remain as bools
    result_direct_true = eval.eval(True)
    assert result_direct_true == True
    assert isinstance(result_direct_true, bool)
    
    result_direct_false = eval.eval(False)
    assert result_direct_false == False
    assert isinstance(result_direct_false, bool)

def test_primitive_type_representation():
    """Test that primitive types use Python string representation."""
    eval = ExprEval()
    eval.set('count', 42)
    eval.set('pi', 3.14)
    eval.set('message', 'hello')
    
    # Integers should be converted to strings using Python's str()
    result_int = eval.eval('count')
    assert result_int == '42', f"Expected '42', got '{result_int}'"
    
    # Floats should be converted to strings using Python's str()
    result_float = eval.eval('pi')
    assert result_float == '3.14', f"Expected '3.14', got '{result_float}'"
    
    # Strings should remain as strings
    result_str = eval.eval('message')
    assert result_str == 'hello', f"Expected 'hello', got '{result_str}'"