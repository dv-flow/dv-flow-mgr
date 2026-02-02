#****************************************************************************
#* produces_eval.py
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
#****************************************************************************

import logging
from typing import Any, Dict, List, Optional
from .expr_eval import ExprEval

class ProducesEvaluator:
    """Evaluates produces patterns by resolving parameter references."""
    
    _log = logging.getLogger("ProducesEvaluator")
    
    def __init__(self, expr_eval: Optional[ExprEval] = None):
        """Initialize with optional ExprEval instance."""
        self._expr_eval = expr_eval or ExprEval()
    
    def evaluate(self, 
                 produces_patterns: List[Dict[str, Any]], 
                 params: Any) -> List[Dict[str, Any]]:
        """
        Evaluates produces patterns by resolving ${{ param }} references.
        
        Args:
            produces_patterns: List of pattern dictionaries with potential references
            params: Task parameters object to resolve references against
            
        Returns:
            List of fully-evaluated pattern dictionaries
        """
        if not produces_patterns:
            return []
        
        evaluated = []
        for pattern in produces_patterns:
            evaluated_pattern = {}
            for key, value in pattern.items():
                if isinstance(value, str):
                    # Check if value contains parameter reference
                    if "${{" in value:
                        try:
                            # Set params in eval scope
                            self._expr_eval.set("params", params)
                            # Evaluate the expression
                            evaluated_value = self._expr_eval.eval(value)
                            evaluated_pattern[key] = evaluated_value
                        except Exception as e:
                            self._log.warning(
                                f"Failed to evaluate produces pattern '{value}': {e}")
                            evaluated_pattern[key] = value
                    else:
                        evaluated_pattern[key] = value
                else:
                    evaluated_pattern[key] = value
            evaluated.append(evaluated_pattern)
        
        return evaluated
