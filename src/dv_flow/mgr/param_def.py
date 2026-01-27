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
from typing import Any, List, Union
from pydantic import BaseModel, Field, model_validator

class ListType(BaseModel):
#    item : Union[str, 'ComplexType']
    item : Union[str, Any]

class MapType(BaseModel):
#    key : Union[str, 'ComplexType']
#    item : Union[str, 'ComplexType']
    key : Union[str, Any]
    val : Union[str, Any]

class ComplexType(BaseModel):
    list : Union[ListType, None] = None
    map : Union[MapType, None] = None
#    list : Union[Any, None] = None
#    map : Union[Any, None] = None

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

