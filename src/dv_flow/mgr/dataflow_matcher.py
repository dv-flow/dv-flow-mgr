#****************************************************************************
#* dataflow_matcher.py
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
from typing import Dict, List, Optional, Tuple, Union
from .task_def import ConsumesE

class DataflowMatcher:
    """Matches producer outputs against consumer inputs."""
    
    _log = logging.getLogger("DataflowMatcher")
    
    def check_compatibility(self, 
                          produces: Optional[List[Dict]],
                          consumes: Union[ConsumesE, List[Dict], None],
                          producer_name: str,
                          consumer_name: str) -> Tuple[bool, Optional[str]]:
        """
        Checks if producer's produces is compatible with consumer's consumes.
        
        Args:
            produces: List of produce patterns from producer task
            consumes: Consume specification from consumer task
            producer_name: Name of producer task (for error messages)
            consumer_name: Name of consumer task (for error messages)
            
        Returns:
            Tuple of (compatible, error_message)
            - compatible: True if compatible or unknown, False for known mismatch
            - error_message: None if compatible, string description if not
        """
        self._log.debug(f"Checking {producer_name} -> {consumer_name}")
        self._log.debug(f"  Produces: {produces}")
        self._log.debug(f"  Consumes: {consumes}")
        
        # No consumes specified - accepts anything
        if consumes is None:
            return (True, None)
        
        # ConsumesE.All - accepts anything
        if isinstance(consumes, ConsumesE):
            if consumes == ConsumesE.All:
                return (True, None)
            elif consumes == ConsumesE.No:
                # Expects no dataflow
                if produces is None or len(produces) == 0:
                    return (True, None)
                else:
                    return (False, 
                           f"Task '{consumer_name}' has consumes=none but "
                           f"'{producer_name}' produces {produces}")
        
        # No produces specified - unknown outputs (assume compatible)
        if produces is None or len(produces) == 0:
            return (True, None)
        
        # Specific consumes patterns - check if ANY consume pattern matches ANY produce pattern (OR logic)
        if isinstance(consumes, list):
            # OR logic: if any consume pattern matches any produce pattern, it's valid
            for consume_pattern in consumes:
                if self._find_matching_produce(consume_pattern, produces):
                    # Found a match - dataflow is valid
                    return (True, None)
            
            # No consume pattern matched any produce pattern
            return (False,
                   f"Task '{consumer_name}' consumes {consumes} but "
                   f"'{producer_name}' produces {produces}. No consume pattern matches any produce pattern.")
        
        return (True, None)
    
    def _find_matching_produce(self, 
                               consume_pattern: Dict, 
                               produces: List[Dict]) -> bool:
        """
        Checks if any produce pattern matches the consume pattern.
        
        A match occurs when all attributes in consume_pattern exist in
        a produce pattern with the same values.
        """
        for produce_pattern in produces:
            if self._pattern_matches(consume_pattern, produce_pattern):
                return True
        return False
    
    def _pattern_matches(self, consume: Dict, produce: Dict) -> bool:
        """
        Checks if a produce pattern satisfies a consume pattern.
        
        All attributes in consume must exist in produce with same value.
        Produce can have additional attributes (subset match).
        """
        for key, value in consume.items():
            if key not in produce:
                self._log.debug(f"  Key '{key}' not in produce")
                return False
            if produce[key] != value:
                self._log.debug(f"  Value mismatch: {produce[key]} != {value}")
                return False
        return True
