#****************************************************************************
#* test_expr_control_flow.py
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
#****************************************************************************
import pytest
from dv_flow.mgr.expr_eval import ExprEval


class TestComparisonOperators:
    """Test comparison operators in expressions"""
    
    def test_equality(self):
        ev = ExprEval()
        ev.set('x', 5)
        ev.set('y', 5)
        ev.set('z', 10)
        
        assert ev.eval('x == y') == 'true'
        assert ev.eval('x == z') == 'false'
        assert ev.eval('x != z') == 'true'
        assert ev.eval('x != y') == 'false'
    
    def test_string_equality(self):
        ev = ExprEval()
        ev.set('status', 'ready')
        
        assert ev.eval('status == "ready"') == 'true'
        assert ev.eval('status == "pending"') == 'false'
        assert ev.eval('status != "pending"') == 'true'
    
    def test_numeric_comparison(self):
        ev = ExprEval()
        ev.set('score', 95)
        ev.set('threshold', 90)
        
        assert ev.eval('score > threshold') == 'true'
        assert ev.eval('score >= threshold') == 'true'
        assert ev.eval('score < threshold') == 'false'
        assert ev.eval('score <= threshold') == 'false'
        assert ev.eval('score >= 95') == 'true'
        assert ev.eval('score > 95') == 'false'


class TestLogicalOperators:
    """Test logical operators (&&, ||, !)"""
    
    def test_and_operator(self):
        ev = ExprEval()
        ev.set('passed', True)
        ev.set('score', 85)
        
        assert ev.eval('passed && score > 80') == 'true'
        assert ev.eval('passed && score > 90') == 'false'
    
    def test_or_operator(self):
        ev = ExprEval()
        ev.set('failed', False)
        ev.set('timeout', True)
        
        assert ev.eval('failed || timeout') == 'true'
        assert ev.eval('failed || !timeout') == 'false'
    
    def test_not_operator(self):
        ev = ExprEval()
        ev.set('error', False)
        ev.set('success', True)
        
        assert ev.eval('!error') == 'true'
        assert ev.eval('!success') == 'false'
    
    def test_complex_logical(self):
        ev = ExprEval()
        ev.set('approved', True)
        ev.set('score', 85)
        ev.set('manual_review', False)
        
        # (approved AND score > 80) OR manual_review
        assert ev.eval('approved && score > 80 || manual_review') == 'true'
        assert ev.eval('!approved && score > 80 || manual_review') == 'false'


class TestBooleanCoercion:
    """Test truthiness/boolean coercion"""
    
    def test_empty_values_are_false(self):
        ev = ExprEval()
        ev.set('empty_string', '')
        ev.set('zero', 0)
        ev.set('empty_list', [])
        ev.set('empty_dict', {})
        ev.set('none_val', None)
        
        assert ev.eval('!empty_string') == 'true'
        assert ev.eval('!zero') == 'true'
        assert ev.eval('!empty_list') == 'true'
        assert ev.eval('!empty_dict') == 'true'
        assert ev.eval('!none_val') == 'true'
    
    def test_non_empty_values_are_true(self):
        ev = ExprEval()
        ev.set('text', 'hello')
        ev.set('number', 42)
        ev.set('items', [1, 2, 3])
        
        assert ev.eval('!!text') == 'true'  # double negation
        assert ev.eval('!!number') == 'true'
        assert ev.eval('!!items') == 'true'


class TestArithmetic:
    """Test arithmetic operations"""
    
    def test_addition(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        
        assert ev.eval('a + b') == '15'
        assert ev.eval('a + 3') == '13'
    
    def test_subtraction(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        
        assert ev.eval('a - b') == '5'
        assert ev.eval('a - 3') == '7'
    
    def test_multiplication(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        
        assert ev.eval('a * b') == '50'
        assert ev.eval('a * 2') == '20'
    
    def test_division(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        
        assert ev.eval('a / b') == '2.0'


class TestComplexExpressions:
    """Test complex expressions combining multiple operators"""
    
    def test_precedence(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        ev.set('c', 2)
        
        # Multiplication before addition
        assert ev.eval('a + b * c') == '20'
        # Comparison after arithmetic
        assert ev.eval('a + b > 10') == 'true'
    
    def test_parentheses(self):
        ev = ExprEval()
        ev.set('a', 10)
        ev.set('b', 5)
        ev.set('c', 2)
        
        assert ev.eval('(a + b) * c') == '30'
        assert ev.eval('a + (b * c)') == '20'
    
    def test_real_world_condition(self):
        """Test a condition like what would be used in control flow"""
        ev = ExprEval()
        ev.set('state', {
            'review_passed': True,
            'iteration': 3,
            'max_iterations': 5
        })
        
        # Simulate: state.review_passed == true
        result = ev.eval('state.review_passed == true')
        assert result == 'true'
        
        # Simulate: state.iteration < state.max_iterations
        result = ev.eval('state.iteration < state.max_iterations')
        assert result == 'true'
