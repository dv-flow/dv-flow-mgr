"""Tests for jq-style builtin functions"""

import pytest
import json
from src.dv_flow.mgr.expr_eval import ExprEval


class TestBuiltinLength:
    """Test length() builtin"""
    
    def test_length_of_array(self):
        evaluator = ExprEval()
        evaluator.set("arr", [1, 2, 3, 4, 5])
        # Call length with variable as argument
        result = evaluator.eval("length(arr)")
        assert result == "5"
    
    def test_length_of_string(self):
        evaluator = ExprEval()
        result = evaluator.eval('length("hello world")')
        assert result == "11"
    
    def test_length_of_object_via_variable(self):
        evaluator = ExprEval()
        evaluator.set("obj", {"a": 1, "b": 2, "c": 3})
        # Note: Can't pass object literal directly, use variable
        evaluator.value = {"a": 1, "b": 2, "c": 3}
        result = evaluator.methods['length'](evaluator.value, [])
        assert result == 3
    
    def test_length_of_empty_array(self):
        evaluator = ExprEval()
        evaluator.set("arr", [])
        result = evaluator.eval("length(arr)")
        assert result == "0"


class TestBuiltinKeys:
    """Test keys() builtin"""
    
    def test_keys_via_method(self):
        evaluator = ExprEval()
        evaluator.value = {"name": "Alice", "age": 30, "city": "NYC"}
        result = evaluator.methods['keys'](evaluator.value, [])
        assert result == ["age", "city", "name"]  # Sorted
    
    def test_keys_of_array(self):
        evaluator = ExprEval()
        evaluator.value = ["a", "b", "c"]
        result = evaluator.methods['keys'](evaluator.value, [])
        assert result == [0, 1, 2]


class TestBuiltinValues:
    """Test values() builtin"""
    
    def test_values_of_object(self):
        evaluator = ExprEval()
        evaluator.value = {"a": 1, "b": 2, "c": 3}
        result = evaluator.methods['values'](evaluator.value, [])
        assert sorted(result) == [1, 2, 3]
    
    def test_values_of_array(self):
        evaluator = ExprEval()
        evaluator.value = [10, 20, 30]
        result = evaluator.methods['values'](evaluator.value, [])
        assert result == [10, 20, 30]


class TestBuiltinSort:
    """Test sort() builtin"""
    
    def test_sort_numbers(self):
        evaluator = ExprEval()
        evaluator.value = [3, 1, 4, 1, 5, 9, 2, 6]
        result = evaluator.methods['sort'](evaluator.value, [])
        assert result == [1, 1, 2, 3, 4, 5, 6, 9]
    
    def test_sort_strings(self):
        evaluator = ExprEval()
        evaluator.value = ["zebra", "apple", "banana"]
        result = evaluator.methods['sort'](evaluator.value, [])
        assert result == ["apple", "banana", "zebra"]
    
    def test_sort_empty_array(self):
        evaluator = ExprEval()
        evaluator.value = []
        result = evaluator.methods['sort'](evaluator.value, [])
        assert result == []


class TestBuiltinUnique:
    """Test unique() builtin"""
    
    def test_unique_numbers(self):
        evaluator = ExprEval()
        evaluator.value = [1, 2, 2, 3, 1, 4, 3]
        result = evaluator.methods['unique'](evaluator.value, [])
        assert result == [1, 2, 3, 4]
    
    def test_unique_strings(self):
        evaluator = ExprEval()
        evaluator.value = ["a", "b", "a", "c", "b"]
        result = evaluator.methods['unique'](evaluator.value, [])
        assert result == ["a", "b", "c"]
    
    def test_unique_preserves_order(self):
        evaluator = ExprEval()
        evaluator.value = [3, 1, 2, 1, 3]
        result = evaluator.methods['unique'](evaluator.value, [])
        assert result == [3, 1, 2]


class TestBuiltinReverse:
    """Test reverse() builtin"""
    
    def test_reverse_array(self):
        evaluator = ExprEval()
        evaluator.value = [1, 2, 3, 4, 5]
        result = evaluator.methods['reverse'](evaluator.value, [])
        assert result == [5, 4, 3, 2, 1]
    
    def test_reverse_string(self):
        evaluator = ExprEval()
        evaluator.value = "hello"
        result = evaluator.methods['reverse'](evaluator.value, [])
        assert result == "olleh"
    
    def test_reverse_empty_array(self):
        evaluator = ExprEval()
        evaluator.value = []
        result = evaluator.methods['reverse'](evaluator.value, [])
        assert result == []


class TestBuiltinFirstLast:
    """Test first() and last() builtins"""
    
    def test_first_element(self):
        evaluator = ExprEval()
        evaluator.value = [10, 20, 30]
        result = evaluator.methods['first'](evaluator.value, [])
        assert result == 10
    
    def test_last_element(self):
        evaluator = ExprEval()
        evaluator.value = [10, 20, 30]
        result = evaluator.methods['last'](evaluator.value, [])
        assert result == 30
    
    def test_first_of_empty_array(self):
        evaluator = ExprEval()
        evaluator.value = []
        result = evaluator.methods['first'](evaluator.value, [])
        assert result is None
    
    def test_last_of_empty_array(self):
        evaluator = ExprEval()
        evaluator.value = []
        result = evaluator.methods['last'](evaluator.value, [])
        assert result is None


class TestBuiltinFlatten:
    """Test flatten() builtin"""
    
    def test_flatten_one_level(self):
        evaluator = ExprEval()
        evaluator.value = [[1, 2], [3, 4], [5]]
        result = evaluator.methods['flatten'](evaluator.value, [])
        assert result == [1, 2, 3, 4, 5]
    
    def test_flatten_nested(self):
        evaluator = ExprEval()
        evaluator.value = [[1, [2, 3]], [4, [5, 6]]]
        result = evaluator.methods['flatten'](evaluator.value, [])
        # Only flattens one level by default
        assert result == [1, [2, 3], 4, [5, 6]]
    
    def test_flatten_with_depth(self):
        evaluator = ExprEval()
        evaluator.value = [[1, [2, 3]], [4, [5, 6]]]
        result = evaluator.methods['flatten'](evaluator.value, [2])
        assert result == [1, 2, 3, 4, 5, 6]
    
    def test_flatten_empty(self):
        evaluator = ExprEval()
        evaluator.value = []
        result = evaluator.methods['flatten'](evaluator.value, [])
        assert result == []


class TestBuiltinType:
    """Test type() builtin"""
    
    def test_type_null(self):
        evaluator = ExprEval()
        evaluator.value = None
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "null"
    
    def test_type_boolean(self):
        evaluator = ExprEval()
        evaluator.value = True
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "boolean"
    
    def test_type_number(self):
        evaluator = ExprEval()
        evaluator.value = 42
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "number"
    
    def test_type_string(self):
        evaluator = ExprEval()
        evaluator.value = "hello"
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "string"
    
    def test_type_array(self):
        evaluator = ExprEval()
        evaluator.value = [1, 2, 3]
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "array"
    
    def test_type_object(self):
        evaluator = ExprEval()
        evaluator.value = {"key": "value"}
        result = evaluator.methods['type'](evaluator.value, [])
        assert result == "object"


class TestBuiltinViaPipeOperator:
    """Test using builtins through filter definitions"""
    
    def test_builtin_as_simple_filter(self):
        """Test that builtin functions work as expression filters"""
        from src.dv_flow.mgr.filter_def import FilterDef
        from src.dv_flow.mgr.filter_registry import FilterRegistry
        
        # Create filter that uses builtin
        filter_def = FilterDef(
            name="array_length",
            expr="length(input)"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("data", [1, 2, 3, 4, 5])
        result = evaluator.eval("data | array_length")
        
        assert result == "5"


class TestBuiltinErrorHandling:
    """Test error handling for builtins"""
    
    def test_sort_non_array_error(self):
        evaluator = ExprEval()
        evaluator.value = "not an array"
        with pytest.raises(Exception, match="sort\\(\\) requires array input"):
            evaluator.methods['sort'](evaluator.value, [])
    
    def test_keys_invalid_type_error(self):
        evaluator = ExprEval()
        evaluator.value = 42
        with pytest.raises(Exception, match="keys\\(\\) cannot be applied"):
            evaluator.methods['keys'](evaluator.value, [])
    
    def test_first_non_array_error(self):
        evaluator = ExprEval()
        evaluator.value = "string"
        with pytest.raises(Exception, match="first\\(\\) requires array input"):
            evaluator.methods['first'](evaluator.value, [])
    
    def test_length_with_too_many_arguments_error(self):
        evaluator = ExprEval()
        evaluator.value = [1, 2, 3]
        with pytest.raises(Exception, match="length\\(\\) takes at most one argument"):
            evaluator.methods['length'](evaluator.value, [5, 6])
