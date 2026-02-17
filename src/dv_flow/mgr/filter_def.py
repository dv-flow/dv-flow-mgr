#****************************************************************************
#* filter_def.py
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
"""
FilterDef - Pydantic model for package-level filter definitions.

Filters are reusable data transformations that can be applied to inputs
in task parameter expressions using the pipe operator (|).
"""
import pydantic.dataclasses as dc
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Dict, List, Union, Optional
from .param_def import ParamDef
from .srcinfo import SrcInfo


class FilterDef(BaseModel):
    """
    Package-level filter definition.
    
    Filters enable reusable data transformations in expressions:
        ${{ inputs | filter_name(arg1, key: val) }}
    
    Visibility control matches task visibility:
    - name: Default visibility (visible within package and to root)
    - local: Fragment-only filter
    - export: Visible to downstream packages
    - root: Root package only
    """
    model_config = ConfigDict(extra='forbid')
    
    # Visibility markers (inline, mutually exclusive)
    name: Optional[str] = Field(
        default=None,
        title="Filter Name",
        description="The name of the filter (default visibility)")
    
    root: Optional[str] = Field(
        default=None,
        title="Root Filter Name",
        description="The name of the filter (marked as root scope)")
    
    export: Optional[str] = Field(
        default=None,
        title="Export Filter Name",
        description="The name of the filter (marked as export scope)")
    
    local: Optional[str] = Field(
        default=None,
        title="Local Filter Name",
        description="The name of the filter (marked as local scope)")
    
    # Alternative explicit visibility
    scope: Optional[Union[str, List[str]]] = Field(
        default=None,
        title="Filter visibility scope",
        description="Visibility scope: 'root', 'export', 'local', or list of package names")
    
    # Parameters (reuses ParamDef via 'with:')
    params: Optional[Dict[str, ParamDef]] = Field(
        default=None,
        alias="with",
        description="Filter parameters. Keys are parameter names, values are ParamDef specifications")
    
    # Documentation
    desc: Optional[str] = Field(
        default="",
        title="Filter description",
        description="Short description of the filter's purpose")
    
    doc: Optional[str] = Field(
        default="",
        title="Filter documentation",
        description="Full documentation of the filter")
    
    # Implementation (mutually exclusive)
    expr: Optional[str] = Field(
        default=None,
        description="jq-style expression implementation (default)")
    
    run: Optional[str] = Field(
        default=None,
        description="Shell or Python script implementation")
    
    shell: str = Field(
        default="bash",
        description="Interpreter for 'run' implementation (bash, python, python3, etc.)")
    
    # Source information
    srcinfo: Optional[SrcInfo] = Field(default=None)
    
    @model_validator(mode='before')
    @classmethod
    def consolidate_name_and_scope(cls, data):
        """
        Consolidate inline scope markers (root, export, local) into name and scope fields.
        Mirrors TaskDef behavior for consistency.
        """
        if not isinstance(data, dict):
            return data
        
        # Check which visibility markers are set
        markers = {
            'name': (data.get('name'), None),
            'root': (data.get('root'), 'root'),
            'export': (data.get('export'), 'export'),
            'local': (data.get('local'), 'local')
        }
        
        set_markers = [(k, v[0], v[1]) for k, v in markers.items() if v[0] is not None]
        
        if len(set_markers) > 1:
            marker_names = [k for k, _, _ in set_markers]
            raise ValueError(
                f"Filter definition has multiple visibility markers: {marker_names}. "
                f"Use only one of: name, root, export, local"
            )
        
        if len(set_markers) == 1:
            marker_key, marker_value, scope_value = set_markers[0]
            
            # Set name to the marker's value
            data['name'] = marker_value
            
            # Set scope if marker specifies one
            if scope_value:
                # Don't override explicit scope if set
                if 'scope' not in data or data['scope'] is None:
                    data['scope'] = scope_value
            
            # Clear other markers
            for k in ['root', 'export', 'local']:
                if k != 'name' and k in data:
                    data[k] = None
        
        # Validate that scope requires name
        if data.get('scope') is not None and data.get('name') is None:
            raise ValueError("'scope' requires 'name' to be set")
        
        return data
    
    @model_validator(mode='after')
    def validate_implementation(self):
        """Ensure exactly one implementation type is specified"""
        impl_count = sum([
            self.expr is not None,
            self.run is not None
        ])
        
        if impl_count == 0:
            raise ValueError(
                f"Filter '{self.name}': must specify either 'expr' (jq expression) or 'run' (script)"
            )
        
        if impl_count > 1:
            raise ValueError(
                f"Filter '{self.name}': 'expr' and 'run' are mutually exclusive. "
                f"Use one or the other, not both"
            )
        
        return self
    
    @model_validator(mode='after')
    def validate_name_set(self):
        """Ensure filter has a name after consolidation"""
        if self.name is None:
            raise ValueError(
                "Filter definition must have a name. Use 'name:', 'local:', 'export:', or 'root:'"
            )
        return self
    
    def get_effective_scope(self) -> Union[str, List[str], None]:
        """
        Get the effective visibility scope for this filter.
        
        Returns:
            'root', 'export', 'local', list of package names, or None (default visibility)
        """
        return self.scope
    
    def is_visible_to(self, requesting_package: str, root_package: str) -> bool:
        """
        Check if this filter is visible to a requesting package.
        
        Args:
            requesting_package: Name of the package requesting access
            root_package: Name of the root package
            
        Returns:
            True if filter is visible to requesting package
        """
        scope = self.get_effective_scope()
        
        if scope is None:
            # Default visibility: visible within package and to root
            return True
        
        if scope == 'root':
            # Only visible to root package
            return requesting_package == root_package
        
        if scope == 'export':
            # Visible to all downstream packages
            return True
        
        if scope == 'local':
            # Only visible within defining package (fragment-only)
            return False
        
        if isinstance(scope, list):
            # Explicit list of packages
            return requesting_package in scope
        
        return False
