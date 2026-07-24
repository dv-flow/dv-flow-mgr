#****************************************************************************
#* param_def.py
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
import enum
import logging as _logging
from typing import Any, List, Union
from pydantic import BaseModel, Field, model_validator

class ListType(BaseModel):
    item : Union[str, Any]

class MapType(BaseModel):
    key : Union[str, Any]
    val : Union[str, Any]

class ComplexType(BaseModel):
    list : Union[ListType, None] = None
    map : Union[MapType, None] = None

class VisibilityE(enum.Enum):
    LOCAL = "local"
    EXPORT = "export"

class ParamDef(BaseModel):
    doc : str = Field(
        default=None,
        description="Full documentation for this parameter")
    desc : str = Field(
        default=None,
        description="Short description of this parameter")
    type : Union[str, 'ComplexType'] = Field(
        default=None,
        description="Parameter type (e.g., 'str', 'int', 'bool', 'list', 'map', or a complex type definition)")
    value : Union[Any, None] = Field(
        default=None,
        description="Default value for this parameter")
    append : Union[Any, None] = Field(
        default=None,
        description="Value to append to list-type parameters")
    prepend : Union[Any, None] = Field(
        default=None,
        description="Value to prepend to list-type parameters")
    path_append : Union[Any, None] = Field(
        alias="path-append", 
        default=None,
        description="Path to append to path-type parameters (OS-specific separator)")
    path_prepend : Union[Any, None] = Field(
        alias="path-prepend", 
        default=None,
        description="Path to prepend to path-type parameters (OS-specific separator)")
    srcinfo : Union[str, None] = Field(alias="srcinfo", default=None)

    def resolve_value(self, base_value):
        """Apply value/prepend/append/path-prepend/path-append against
        *base_value*.

        When 'value' is set, it replaces base_value as the starting point.
        Then the list ops are layered on top:
            result = path_prepend + prepend + (value or base) + append + path_append

        For list-typed params (the common case: `plusargs`, `incdirs`, ...) the
        path-* ops add elements just like prepend/append. (OS-path-separator
        *string* join for scalar PATH-like params is a documented follow-up in
        docs/proposals/list_manipulation.md; no current flow relies on it.)
        """
        def _as_items(v):
            return v if isinstance(v, list) else [v]

        if self.value is not None:
            result = list(self.value) if isinstance(self.value, list) \
                     else [self.value]
        else:
            result = list(base_value) if isinstance(base_value, list) \
                     else ([base_value] if base_value else [])
        if self.prepend is not None:
            result = _as_items(self.prepend) + result
        if self.append is not None:
            result = result + _as_items(self.append)
        if self.path_prepend is not None:
            result = _as_items(self.path_prepend) + result
        if self.path_append is not None:
            result = result + _as_items(self.path_append)
        # If only value was set (no list op), return as-is (preserve scalars).
        if not self.has_list_op() and self.value is not None:
            return self.value
        return result

    def has_list_op(self) -> bool:
        """True when this ParamDef carries a list op (append/prepend or their
        path-* variants)."""
        return (self.append is not None or self.prepend is not None
                or self.path_append is not None or self.path_prepend is not None)

