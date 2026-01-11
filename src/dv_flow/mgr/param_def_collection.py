#****************************************************************************
#* param_def_collection.py
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
import dataclasses as dc
from typing import Dict, Optional, Any
from .param_def import ParamDef
from .srcinfo import SrcInfo

@dc.dataclass
class ParamDefCollection:
    """
    Holds unevaluated parameter definitions for a task.
    Replaces eager paramT creation during loading.
    """
    # Maps parameter name to its definition (with unevaluated template expressions)
    definitions: Dict[str, ParamDef] = dc.field(default_factory=dict)
    
    # Maps parameter name to its type annotation
    types: Dict[str, type] = dc.field(default_factory=dict)
    
    # Source location for error reporting
    srcinfo: Optional[SrcInfo] = None
    
    def add_param(self, name: str, param_def: ParamDef, param_type: type):
        """Add a parameter definition"""
        self.definitions[name] = param_def
        self.types[name] = param_type
    
    def has_param(self, name: str) -> bool:
        """Check if parameter is defined"""
        return name in self.definitions
    
    def get_param(self, name: str) -> Optional[ParamDef]:
        """Get parameter definition"""
        return self.definitions.get(name)
    
    def get_type(self, name: str) -> Optional[type]:
        """Get parameter type"""
        return self.types.get(name)
