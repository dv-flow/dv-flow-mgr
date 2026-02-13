#****************************************************************************
#* test_deferred_expr.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*  
#*   http://www.apache.org/licenses/LICENSE-2.0
#*  
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import pytest
from dv_flow.mgr.deferred_expr import DeferredExpr, references_runtime_data
from dv_flow.mgr.expr_parser import ExprParser
from dv_flow.mgr.expr_eval import ExprEval


class TestDeferredExpr:
    """Tests for DeferredExpr class"""
    
    def test_basic_creation(self):
        """Test basic deferred expression creation"""
        parser = ExprParser()
        expr_str = "${{ inputs }}"
        ast = parser.parse(expr_str)
        
        deferred = DeferredExpr(expr_str, ast, {"foo": "bar"})
        
        assert deferred.expr_str == expr_str
        assert deferred.expr_ast is ast
        assert deferred.static_context == {"foo": "bar"}
    
    def test_evaluation_with_runtime_context(self):
        """Test evaluating deferred expression with runtime data"""
        parser = ExprParser()
        expr_str = "${{ inputs }}"
        ast = parser.parse(expr_str)
        
        # Create deferred expression with static context
        static_ctx = {"static_var": 123}
        deferred = DeferredExpr(expr_str, ast, static_ctx)
        
        # Create evaluator
        evaluator = ExprEval()
        
        # Evaluate with runtime context
        runtime_ctx = {"inputs": [{"name": "file1"}, {"name": "file2"}]}
        result = deferred.evaluate(evaluator, runtime_ctx)
        
        assert result == runtime_ctx["inputs"]
    
    def test_runtime_overrides_static(self):
        """Test that runtime context takes precedence over static"""
        parser = ExprParser()
        expr_str = "${{ value }}"
        ast = parser.parse(expr_str)
        
        # Both contexts have 'value', runtime should win
        static_ctx = {"value": "static"}
        deferred = DeferredExpr(expr_str, ast, static_ctx)
        
        evaluator = ExprEval()
        runtime_ctx = {"value": "runtime"}
        result = deferred.evaluate(evaluator, runtime_ctx)
        
        assert result == "runtime"
    
    def test_string_representation(self):
        """Test __str__ and __repr__"""
        parser = ExprParser()
        expr_str = "${{ inputs | filter }}"
        ast = parser.parse(expr_str)
        
        deferred = DeferredExpr(expr_str, ast)
        
        assert str(deferred) == expr_str
        assert "DeferredExpr" in repr(deferred)
        assert expr_str in repr(deferred)


class TestReferencesRuntimeData:
    """Tests for runtime data reference detection"""
    
    def test_detects_inputs_reference(self):
        """Test detection of 'inputs' reference"""
        parser = ExprParser()
        
        # Simple identifier
        ast = parser.parse("${{ inputs }}")
        assert references_runtime_data(ast) is True
        
        # Hierarchical access
        ast = parser.parse("${{ inputs.field }}")
        assert references_runtime_data(ast) is True
    
    def test_detects_memento_reference(self):
        """Test detection of 'memento' reference"""
        parser = ExprParser()
        
        ast = parser.parse("${{ memento }}")
        assert references_runtime_data(ast) is True
        
        ast = parser.parse("${{ memento.cached_value }}")
        assert references_runtime_data(ast) is True
    
    def test_no_runtime_reference_for_static_vars(self):
        """Test that static variables don't trigger detection"""
        parser = ExprParser()
        
        # Static variable
        ast = parser.parse("${{ my_var }}")
        assert references_runtime_data(ast) is False
        
        # Hierarchical static var
        ast = parser.parse("${{ pkg.param.value }}")
        assert references_runtime_data(ast) is False
    
    def test_detects_in_binary_expressions(self):
        """Test detection in binary operations"""
        parser = ExprParser()
        
        # Arithmetic with inputs
        ast = parser.parse("${{ inputs + 10 }}")
        assert references_runtime_data(ast) is True
        
        # Comparison with static
        ast = parser.parse("${{ my_var > 5 }}")
        assert references_runtime_data(ast) is False
    
    def test_detects_in_function_calls(self):
        """Test detection in method calls"""
        parser = ExprParser()
        
        # Method call with inputs
        ast = parser.parse("${{ shell(inputs) }}")
        assert references_runtime_data(ast) is True
        
        # Method call without runtime data
        ast = parser.parse("${{ shell('echo hello') }}")
        assert references_runtime_data(ast) is False
    
    def test_custom_runtime_vars(self):
        """Test detection with custom runtime variable set"""
        parser = ExprParser()
        
        ast = parser.parse("${{ custom_runtime_var }}")
        
        # Default runtime vars don't include 'custom_runtime_var'
        assert references_runtime_data(ast) is False
        
        # But should detect with custom set
        assert references_runtime_data(ast, {'custom_runtime_var'}) is True
    
    def test_complex_expression_with_multiple_refs(self):
        """Test complex expression with both static and runtime refs"""
        parser = ExprParser()
        
        # Expression mixing static and runtime
        ast = parser.parse("${{ static_var + inputs.count }}")
        assert references_runtime_data(ast) is True
        
        # Pure static expression
        ast = parser.parse("${{ var1 + var2 * 3 }}")
        assert references_runtime_data(ast) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
