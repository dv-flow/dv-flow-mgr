#****************************************************************************
#* searcher.py
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
"""Search and filter utilities for show commands."""

import re
from typing import List, Optional, Dict, Any


class Searcher:
    """Search and filter utility for packages, tasks, and types."""
    
    def __init__(self, 
                 keyword: Optional[str] = None,
                 regex: Optional[str] = None,
                 tag_filter: Optional[str] = None):
        self._keywords = keyword.lower().split() if keyword else None
        self._regex_pattern = re.compile(regex, re.IGNORECASE) if regex else None
        self._tag_filter = self._parse_tag_filter(tag_filter) if tag_filter else None
    
    def matches(self, name: str, desc: Optional[str], doc: Optional[str], 
                tags: Optional[List[Any]] = None) -> bool:
        """Check if item matches all search criteria."""
        # All conditions must match (AND logic)
        if self._keywords and not self._matches_keywords(name, desc, doc):
            return False
        if self._regex_pattern and not self._matches_regex(desc, doc):
            return False
        if self._tag_filter and not self._matches_tag(tags):
            return False
        return True
    
    def _matches_keywords(self, name: str, desc: Optional[str], doc: Optional[str]) -> bool:
        """Check if all keywords match in name, desc, or doc."""
        search_text = ' '.join([
            name.lower() if name else '',
            (desc or '').lower(),
            (doc or '').lower()
        ])
        return all(kw in search_text for kw in self._keywords)
    
    def _matches_regex(self, desc: Optional[str], doc: Optional[str]) -> bool:
        """Check if regex matches in desc or doc."""
        search_text = ' '.join([desc or '', doc or ''])
        return bool(self._regex_pattern.search(search_text))
    
    def _matches_tag(self, tags: Optional[List[Any]]) -> bool:
        """Check if any tag matches the filter."""
        if not tags:
            return False
        
        tag_type = self._tag_filter.get('type')
        field = self._tag_filter.get('field')
        value = self._tag_filter.get('value')
        
        for tag in tags:
            # Handle different tag representations
            if isinstance(tag, str):
                # Simple string tag
                tag_name = tag
                tag_params = {}
            elif isinstance(tag, dict):
                # Dict with type name as key
                tag_name = list(tag.keys())[0] if tag else ''
                tag_params = tag.get(tag_name, {})
            else:
                # Object with name/params attributes
                tag_name = getattr(tag, 'name', str(tag))
                tag_params = {}
                if hasattr(tag, 'paramT'):
                    pt = tag.paramT
                    tag_params = {
                        'category': getattr(pt, 'category', ''),
                        'value': getattr(pt, 'value', '')
                    }
            
            # Match by type name
            if tag_type:
                # Allow partial match (e.g., "Priority" matches "myproject.Priority")
                if not (tag_name == tag_type or tag_name.endswith('.' + tag_type)):
                    continue
            
            # If only type specified, it's a match
            if not field and not value:
                return True
            
            # Match by field=value
            if field and value:
                if tag_params.get(field) == value:
                    return True
            elif value:
                # Shorthand: category:value format
                if tag_params.get('category') == self._tag_filter.get('category') and \
                   tag_params.get('value') == value:
                    return True
        
        return False
    
    def _parse_tag_filter(self, tag_str: str) -> Dict[str, Optional[str]]:
        """Parse tag filter string.
        
        Formats:
        - "TagType" - match by type name
        - "TagType:field=value" - match by type and field value
        - "category:value" - shorthand for std.Tag with category/value
        """
        result = {'type': None, 'field': None, 'value': None, 'category': None}
        
        if ':' in tag_str:
            parts = tag_str.split(':', 1)
            first_part = parts[0]
            second_part = parts[1]
            
            if '=' in second_part:
                # TagType:field=value format
                result['type'] = first_part
                field_val = second_part.split('=', 1)
                result['field'] = field_val[0]
                result['value'] = field_val[1]
            else:
                # category:value shorthand
                result['category'] = first_part
                result['value'] = second_part
                result['field'] = 'category'  # Will check category field
        else:
            # Just type name
            result['type'] = tag_str
        
        return result


def filter_by_scope(items: List[Dict[str, Any]], scope: Optional[str]) -> List[Dict[str, Any]]:
    """Filter items by visibility scope."""
    if not scope:
        return items
    
    result = []
    for item in items:
        item_scope = item.get('scope', [])
        if isinstance(item_scope, str):
            item_scope = [item_scope]
        if scope in item_scope:
            result.append(item)
    return result


def filter_by_package(items: List[Dict[str, Any]], package: Optional[str]) -> List[Dict[str, Any]]:
    """Filter items by package name."""
    if not package:
        return items
    return [item for item in items if item.get('package') == package]
