"""Tests for jq-style array and object indexing"""

import pytest
from dv_flow.mgr.expr_parser import ExprParser
from dv_flow.mgr.expr_eval import ExprEval


class TestArrayIndexing:
    """Test array indexing operations"""
    
    def test_simple_index(self):
        """Test basic array indexing"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c"])
        
        ast = parser.parse("arr[0]")
        ast.accept(evaluator)
        assert evaluator.value == "a"
        
        ast = parser.parse("arr[1]")
        ast.accept(evaluator)
        assert evaluator.value == "b"
    
    def test_out_of_bounds(self):
        """Test index out of bounds"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c"])
        
        ast = parser.parse("arr[10]")
        with pytest.raises(Exception, match="Index"):
            ast.accept(evaluator)


class TestArraySlicing:
    """Test array slicing operations"""
    
    def test_basic_slice(self):
        """Test basic slice [start:end]"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c", "d", "e"])
        
        ast = parser.parse("arr[1:3]")
        ast.accept(evaluator)
        assert evaluator.value == ["b", "c"]
    
    def test_slice_from_start(self):
        """Test slice from beginning [:end]"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c", "d", "e"])
        
        ast = parser.parse("arr[:2]")
        ast.accept(evaluator)
        assert evaluator.value == ["a", "b"]
    
    def test_slice_to_end(self):
        """Test slice to end [start:]"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c", "d", "e"])
        
        ast = parser.parse("arr[3:]")
        ast.accept(evaluator)
        assert evaluator.value == ["d", "e"]


class TestObjectIndexing:
    """Test object (dictionary) indexing"""
    
    def test_string_key_access(self):
        """Test accessing object with string key"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("obj", {"name": "Alice", "age": 30})
        
        ast = parser.parse("obj['name']")
        ast.accept(evaluator)
        assert evaluator.value == "Alice"
        
        ast = parser.parse("obj['age']")
        ast.accept(evaluator)
        assert evaluator.value == 30


class TestArrayIterator:
    """Test array iterator []"""
    
    def test_iterate_array(self):
        """Test iterating over array with []"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("arr", ["a", "b", "c"])
        
        ast = parser.parse("arr[]")
        ast.accept(evaluator)
        assert evaluator.value == ["a", "b", "c"]
    
    def test_iterate_object(self):
        """Test iterating over object returns values"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("obj", {"a": 1, "b": 2, "c": 3})
        
        ast = parser.parse("obj[]")
        ast.accept(evaluator)
        # Result should be values (order may vary for dict)
        assert set(evaluator.value) == {1, 2, 3}


class TestNestedIndexing:
    """Test complex nested indexing"""
    
    def test_nested_array_access(self):
        """Test accessing nested arrays"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("data", [["a", "b"], ["c", "d"]])
        
        ast = parser.parse("data[0][1]")
        ast.accept(evaluator)
        assert evaluator.value == "b"
    
    def test_object_then_array(self):
        """Test object field access then array index"""
        parser = ExprParser()
        evaluator = ExprEval()
        evaluator.set("data", {"users": ["Alice", "Bob", "Charlie"]})
        
        ast = parser.parse("data.users[1]")
        ast.accept(evaluator)
        assert evaluator.value == "Bob"
