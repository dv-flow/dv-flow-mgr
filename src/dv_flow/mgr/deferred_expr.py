#****************************************************************************
#* deferred_expr.py
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
from typing import Any, Dict, Optional
from .expr_parser import Expr

class DeferredExpr:
    """
    Represents an expression that must be evaluated at runtime rather than
    during graph construction. This is needed for expressions that reference
    runtime-only data such as 'inputs' (dependency outputs) or 'memento'
    (cached data from previous runs).
    
    The expression is stored as both a string and parsed AST, along with
    the static evaluation context captured at graph build time.
    """
    
    def __init__(self, expr_str: str, expr_ast: Expr, static_context: Optional[Dict[str, Any]] = None):
        """
        Create a deferred expression.
        
        Args:
            expr_str: Original expression string (e.g., "${{ inputs | filter }}")
            expr_ast: Parsed expression AST
            static_context: Static variables captured at graph build time
        """
        self.expr_str = expr_str
        self.expr_ast = expr_ast
        self.static_context = static_context or {}
    
    def evaluate(self, evaluator, runtime_context: Dict[str, Any]) -> Any:
        """
        Evaluate the deferred expression with runtime context.
        
        Args:
            evaluator: ExprEval instance to use for evaluation
            runtime_context: Runtime variables (inputs, memento, etc.)
            
        Returns:
            Evaluated result
        """
        # Merge static and runtime contexts
        # Runtime context takes precedence for overlapping keys
        merged_context = {**self.static_context, **runtime_context}
        
        # Update evaluator's variable context
        for key, value in merged_context.items():
            evaluator.set(key, value)
        
        # Evaluate the stored AST
        self.expr_ast.accept(evaluator)
        return evaluator.value
    
    def __repr__(self):
        return f"DeferredExpr({self.expr_str})"
    
    def __str__(self):
        return self.expr_str


def references_runtime_data(expr_ast: Expr, runtime_vars: set = None) -> bool:
    """
    Check if an expression AST references runtime-only variables.
    
    Args:
        expr_ast: Parsed expression AST
        runtime_vars: Set of runtime variable names (default: {'inputs', 'memento'})
        
    Returns:
        True if expression references any runtime variables
    """
    if runtime_vars is None:
        runtime_vars = {'inputs', 'memento'}
    
    from .expr_parser import ExprId, ExprHId, ExprBin, ExprUnary, ExprCall, ExprVar
    
    # Recursively check for runtime variable references
    def check(node):
        if isinstance(node, ExprId):
            return node.id in runtime_vars
        elif isinstance(node, ExprVar):
            # Variable reference: $name
            return node.name in runtime_vars
        elif isinstance(node, ExprHId):
            # Check first identifier in hierarchical ID (e.g., 'inputs.field')
            return len(node.id) > 0 and node.id[0] in runtime_vars
        elif isinstance(node, ExprBin):
            return check(node.lhs) or check(node.rhs)
        elif isinstance(node, ExprUnary):
            return check(node.expr)
        elif isinstance(node, ExprCall):
            # Check method name (if it's an identifier) and arguments
            # Note: ExprCall.id is a string, not an expression
            result = node.id in runtime_vars
            for arg in node.args:
                result = result or check(arg)
            return result
        else:
            # For other node types (strings, ints, bools), no runtime reference
            return False
    
    return check(expr_ast)
