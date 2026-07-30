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
    """Matches producer outputs against consumer inputs.

    `resolve_type(name) -> Type | None` enables IS-A matching on `type`, so a
    consumer asking for `std.FileSet` accepts a `std.PubSet`. Without it,
    matching falls back to string equality -- the honest answer when no type
    registry is available, since a matcher with no way to reason about
    inheritance should not start rejecting things.
    """

    _log = logging.getLogger("DataflowMatcher")

    def __init__(self, resolve_type=None):
        self.resolve_type = resolve_type
    
    def check_compatibility(self,
                          produces: Optional[List[Dict]],
                          consumes: Union[ConsumesE, List[Dict], None],
                          producer_name: str,
                          consumer_name: str,
                          passthrough=None) -> Tuple[bool, Optional[str]]:
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
                if produces is None or len(produces) == 0:
                    return (True, None)
                # `consumes: none` means "I do not READ these inputs" -- not
                # "nothing may flow to me". A task that forwards what it does
                # not consume is the ordinary aggregator idiom (`std.FileSet`
                # with `passthrough: all` collecting other filesets), so the
                # items are not dropped and there is nothing to report.
                if self._forwards(passthrough):
                    return (True, None)
                # Neither read nor forwarded: the producer's output really is
                # discarded here, which is worth saying.
                return (False,
                       f"Task '{consumer_name}' consumes none of its inputs and "
                       f"does not pass them through, so the output of "
                       f"'{producer_name}' ({produces}) is discarded")
        
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
    
    @staticmethod
    def _forwards(passthrough) -> bool:
        """Whether a task forwards inputs it did not consume.

        Unspecified means the engine default (`unused`), which forwards.
        """
        if passthrough is None:
            return True
        value = getattr(passthrough, 'value', passthrough)
        return str(value).lower() not in ("none", "false")

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

        Subset match on attributes, IS-A match on `type` -- see
        `type_match.pattern_matches`, which is shared with `std.check.Needs` so
        the two cannot disagree about what satisfies what.
        """
        from .type_match import pattern_matches
        return pattern_matches(consume, produce, self.resolve_type)
