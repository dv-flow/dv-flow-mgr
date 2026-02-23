"""Tests for standard library enhancements - split() and variables"""

import pytest
from dv_flow.mgr.expr_parser import ExprParser
from dv_flow.mgr.expr_eval import ExprEval


class TestVariableSyntax:
    """Test $name variable references"""
    
    def test_simple_variable_reference(self):
        """Test basic $variable syntax"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("name", "Alice")
        ast = parser.parse("$name")
        ast.accept(evaluator)
        
        assert evaluator.value == "Alice"
    
    def test_variable_in_expression(self):
        """Test variable in comparison"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("threshold", 10)
        evaluator.set("value", 15)
        
        ast = parser.parse("value > $threshold")
        ast.accept(evaluator)
        
        assert evaluator.value == True
    
    def test_variable_as_filter_argument(self):
        """Test using variable as argument to builtin"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("sep", "/")
        evaluator.set("path", "/home/user/file.txt")
        
        ast = parser.parse("path | split($sep)")
        ast.accept(evaluator)
        
        assert evaluator.value == ["", "home", "user", "file.txt"]


class TestSplitBuiltin:
    """Test split() JQ builtin"""
    
    def test_split_string_basic(self):
        """Test basic string splitting"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("path", "/home/user/file.txt")
        ast = parser.parse('path | split("/")')
        ast.accept(evaluator)
        
        assert evaluator.value == ["", "home", "user", "file.txt"]
    
    def test_split_with_dot(self):
        """Test splitting on dots"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("filename", "module.core.v")
        ast = parser.parse('filename | split(".")')
        ast.accept(evaluator)
        
        assert evaluator.value == ["module", "core", "v"]
    
    def test_split_then_last(self):
        """Test split followed by last (basename)"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("filepath", "/home/project/design/top.sv")
        ast = parser.parse('filepath | split("/") | last')
        ast.accept(evaluator)
        
        assert evaluator.value == "top.sv"
    
    def test_split_then_first(self):
        """Test split followed by first"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("data", "a:b:c")
        ast = parser.parse('data | split(":") | first')
        ast.accept(evaluator)
        
        assert evaluator.value == "a"
    
    def test_split_then_index(self):
        """Test split followed by array indexing"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("path", "/usr/local/bin")
        ast = parser.parse('path | split("/")[2]')
        ast.accept(evaluator)
        
        assert evaluator.value == "local"


class TestBuiltinPiping:
    """Test that builtins work with pipe operator"""
    
    def test_length_via_pipe(self):
        """Test length builtin via pipe"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("arr", [1, 2, 3, 4, 5])
        ast = parser.parse("arr | length")
        ast.accept(evaluator)
        
        assert evaluator.value == 5
    
    def test_sort_via_pipe(self):
        """Test sort builtin via pipe"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("data", [3, 1, 4, 1, 5])
        ast = parser.parse("data | sort")
        ast.accept(evaluator)
        
        assert evaluator.value == [1, 1, 3, 4, 5]
    
    def test_unique_via_pipe(self):
        """Test unique builtin via pipe"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("data", [1, 2, 2, 3, 1])
        ast = parser.parse("data | unique")
        ast.accept(evaluator)
        
        assert evaluator.value == [1, 2, 3]
    
    def test_chained_builtins(self):
        """Test chaining multiple builtins"""
        parser = ExprParser()
        evaluator = ExprEval()
        
        evaluator.set("data", [3, 1, 2, 1, 3])
        ast = parser.parse("data | unique | sort | reverse")
        ast.accept(evaluator)
        
        assert evaluator.value == [3, 2, 1]


class TestComplexPipelines:
    """Test complex expression pipelines"""
    
