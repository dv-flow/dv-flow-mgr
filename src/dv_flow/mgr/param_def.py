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
    doc : str = None
    type : Union[str, 'ComplexType'] = None
#    derived : bool = Field(default=False)
    value : Union[Any, None] = None
    append : Union[Any, None] = None
    prepend : Union[Any, None] = None
    path_append : Union[Any, None] = Field(alias="path-append", default=None)
    path_prepend : Union[Any, None] = Field(alias="path-prepend", default=None)
    srcinfo : Union[str, None] = Field(alias="srcinfo", default=None)

