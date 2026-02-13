"""Tests for filter evaluation in expressions"""

import pytest
import json
from src.dv_flow.mgr.expr_eval import ExprEval
from src.dv_flow.mgr.filter_def import FilterDef
from src.dv_flow.mgr.filter_registry import FilterRegistry


class TestBasicFilterEvaluation:
    """Test basic filter evaluation with pipe operator"""
    
    def test_simple_jq_expression_filter(self):
        """Test simple jq expression filter"""
        # Create a filter that extracts input value
        filter_def = FilterDef(
            name="identity",
            expr="input"
        )
        
        # Set up registry
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        # Create evaluator with filter support
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        # Set up test data
        evaluator.set("data", {"key": "value"})
        
        # Evaluate: data | identity
        result = evaluator.eval("data | identity")
        
        # Parse result
        result_obj = json.loads(result)
        assert result_obj == {"key": "value"}
    
    def test_filter_with_expression_manipulation(self):
        """Test filter that manipulates input with expression"""
        # Create filter that doubles a number
        filter_def = FilterDef(
            name="double",
            expr="input + input"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("num", 5)
        result = evaluator.eval("num | double")
        
        assert result == "10"
    
    def test_filter_not_found_error(self):
        """Test error when filter doesn't exist"""
        registry = FilterRegistry()
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("data", 42)
        
        with pytest.raises(Exception, match="Filter 'nonexistent' not found"):
            evaluator.eval("data | nonexistent")
    
    def test_no_registry_error(self):
        """Test error when using filter without registry"""
        evaluator = ExprEval()
        evaluator.set("data", 42)
        
        with pytest.raises(Exception, match="no filter registry configured"):
            evaluator.eval("data | some_filter")


class TestPythonFilterEvaluation:
    """Test Python script filter evaluation"""
    
    def test_simple_python_filter(self):
        """Test basic Python filter"""
        filter_def = FilterDef(
            name="to_upper",
            shell="python3",
            run="""
def filter(input_data, **kwargs):
    return input_data.upper()
"""
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("text", "hello")
        result = evaluator.eval("text | to_upper")
        
        assert result == "HELLO"
    
    def test_python_filter_with_json_input(self):
        """Test Python filter with JSON object"""
        filter_def = FilterDef(
            name="extract_name",
            shell="python3",
            run="""
def filter(input_data, **kwargs):
    import json
    if isinstance(input_data, str):
        data = json.loads(input_data)
    else:
        data = input_data
    return data.get('name', 'unknown')
"""
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("obj", {"name": "Alice", "age": 30})
        result = evaluator.eval("obj | extract_name")
        
        assert result == "Alice"
    
    def test_python_filter_missing_function_error(self):
        """Test error when Python filter doesn't define filter function"""
        filter_def = FilterDef(
            name="bad_filter",
            shell="python3",
            run="x = 42"  # No filter function
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("data", 42)
        
        with pytest.raises(Exception, match="must define a 'filter' function"):
            evaluator.eval("data | bad_filter")
    
    def test_python_filter_compilation_error(self):
        """Test error when Python filter has syntax error"""
        filter_def = FilterDef(
            name="syntax_error",
            shell="python3",
            run="def filter(input_data, **kwargs)\n  return input_data"  # Missing colon
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("data", 42)
        
        with pytest.raises(Exception, match="failed to compile"):
            evaluator.eval("data | syntax_error")


class TestShellFilterEvaluation:
    """Test shell script filter evaluation"""
    
    def test_simple_shell_filter(self):
        """Test basic shell filter"""
        filter_def = FilterDef(
            name="count_lines",
            shell="bash",
            run="wc -l | awk '{print $1}'"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("text", "line1\nline2\nline3")
        result = evaluator.eval("text | count_lines")
        
        # wc -l counts the number of newlines, so "line1\nline2\nline3" has 2 newlines
        assert result == "2"
    
    def test_shell_filter_with_jq(self):
        """Test shell filter using jq command"""
        filter_def = FilterDef(
            name="extract_field",
            shell="bash",
            run="jq -r .name"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("data", {"name": "Bob", "age": 25})
        result = evaluator.eval("data | extract_field")
        
        assert result == "Bob"


class TestFilterChaining:
    """Test chaining multiple filters"""
    
    def test_chain_two_filters(self):
        """Test chaining two filters with pipe operator"""
        filter1 = FilterDef(
            name="double",
            expr="input + input"
        )
        
        filter2 = FilterDef(
            name="add_ten",
            expr="input + 10"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter1, filter2], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("num", 5)
        # 5 | double = 10, 10 | add_ten = 20
        result = evaluator.eval("num | double | add_ten")
        
        assert result == "20"
    
    def test_chain_three_filters(self):
        """Test chaining three filters"""
        filter1 = FilterDef(name="double", expr="input + input")
        filter2 = FilterDef(name="double", expr="input + input")  # Use same filter
        filter3 = FilterDef(name="add_one", expr="input + 1")
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter1, filter2, filter3], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("num", 3)
        # 3 | double = 6, 6 | double = 12, 12 | add_one = 13
        result = evaluator.eval("num | double | double | add_one")
        
        assert result == "13"


class TestFilterVisibility:
    """Test filter visibility and qualified names"""
    
    def test_qualified_filter_name(self):
        """Test using qualified filter name"""
        filter_def = FilterDef(
            name="helper",
            expr="input + 100"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("other_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("num", 5)
        result = evaluator.eval("num | other_pkg.helper")
        
        assert result == "105"
    
    def test_local_filter_not_visible(self):
        """Test that local filters are not visible to other packages"""
        filter_def = FilterDef(
            name="local:secret",
            expr="input * 2"
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("pkg_a", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="pkg_b"
        )
        
        evaluator.set("num", 10)
        
        with pytest.raises(Exception, match="Filter 'secret' not found"):
            evaluator.eval("num | secret")


class TestFilterParameters:
    """Test filters with parameters (future enhancement)"""
    
    @pytest.mark.skip(reason="Parameter support not yet implemented")
    def test_filter_with_parameters(self):
        """Test filter that accepts parameters"""
        filter_def = FilterDef(
            name="multiply",
            expr="input * factor",
            params=[{"name": "factor", "type": "int"}]
        )
        
        registry = FilterRegistry()
        registry.register_package_filters("test_pkg", [filter_def], [])
        
        evaluator = ExprEval(
            filter_registry=registry,
            current_package="test_pkg"
        )
        
        evaluator.set("num", 7)
        result = evaluator.eval("num | multiply(3)")
        
        assert result == "21"
