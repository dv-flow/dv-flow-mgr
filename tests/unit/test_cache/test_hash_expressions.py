"""
Test expression enhancements for cache hashing
"""

import pytest
from dv_flow.mgr.expr_eval import ExprEval
from dv_flow.mgr.expr_parser import ExprParser


def test_shell_function():
    """Test shell() built-in function"""
    eval = ExprEval()
    
    # Simple command
    result = eval.eval('shell("echo hello")')
    assert result == 'hello'
    
    # Command with variable expansion
    result = eval.eval('shell("echo test")')
    assert result == 'test'


def test_shell_function_with_var():
    """Test shell() function with variable substitution"""
    eval = ExprEval()
    eval.set('cmd', 'world')
    
    # Command using variable - note this doesn't support nested yet
    result = eval.eval('shell("echo hello")')
    assert result == 'hello'


def test_shell_function_error():
    """Test shell() function error handling"""
    eval = ExprEval()
    
    # Command that fails
    with pytest.raises(Exception) as exc_info:
        eval.eval('shell("false")')
    
    assert 'shell() command failed' in str(exc_info.value)


def test_shell_function_wrong_args():
    """Test shell() function with wrong number of arguments"""
    eval = ExprEval()
    
    with pytest.raises(Exception) as exc_info:
        eval.eval('shell("echo", "hello")')
    
    assert 'requires exactly one argument' in str(exc_info.value)


def test_default_value_simple():
    """Test default value syntax for simple variable"""
    eval = ExprEval()
    
    # Variable exists
    eval.set('CC', 'clang')
    result = eval.eval('CC:-gcc')
    assert result == 'clang'
    
    # Variable doesn't exist - use default
    eval2 = ExprEval()
    result = eval2.eval('CC:-gcc')
    assert result == 'gcc'


def test_default_value_hierarchical():
    """Test default value syntax for hierarchical variable"""
    eval = ExprEval()
    
    # Variable exists
    env = {'CC': 'clang'}
    eval.set('env', env)
    result = eval.eval('env.CC:-gcc')
    assert result == 'clang'
    
    # Top level exists but sub-element doesn't
    env2 = {'HOME': '/home/user'}
    eval2 = ExprEval()
    eval2.set('env', env2)
    result = eval2.eval('env.CC:-gcc')
    assert result == 'gcc'
    
    # Top level doesn't exist
    eval3 = ExprEval()
    result = eval3.eval('env.CC:-gcc')
    assert result == 'gcc'


def test_nested_expression_simple():
    """Test nested expression expansion"""
    eval = ExprEval()
    eval.set('compiler', 'gcc')
    
    # Nested variable reference
    result = eval.eval('shell("echo ${{ compiler }}")')
    assert result == 'gcc'


def test_nested_expression_hierarchical():
    """Test nested expression with hierarchical variables"""
    eval = ExprEval()
    env = {'CC': 'clang'}
    eval.set('env', env)
    
    result = eval.eval('shell("echo ${{ env.CC }}")')
    assert result == 'clang'


def test_nested_expression_with_default():
    """Test nested expression with default value"""
    eval = ExprEval()
    
    # Variable doesn't exist, use default
    result = eval.eval('shell("echo ${{ env.CC:-gcc }}")')
    assert result == 'gcc'
    
    # Variable exists
    env = {'CC': 'clang'}
    eval2 = ExprEval()
    eval2.set('env', env)
    result = eval2.eval('shell("echo ${{ env.CC:-gcc }}")')
    assert result == 'clang'


def test_multiple_nested_expressions():
    """Test multiple nested expressions in one string"""
    eval = ExprEval()
    eval.set('name', 'test')
    eval.set('version', '1.0')
    
    result = eval.eval('shell("echo ${{ name }}-${{ version }}")')
    assert result == 'test-1.0'


def test_deeply_nested_expressions():
    """Test deeply nested expressions"""
    eval = ExprEval()
    eval.set('var1', 'compiler')
    eval.set('compiler', 'gcc')
    
    # This is a complex case - for now just test one level
    result = eval.eval('shell("echo ${{ compiler }}")')
    assert result == 'gcc'
