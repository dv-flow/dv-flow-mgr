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
from typing import Any, List, Union
from pydantic import BaseModel, Field

class ListType(BaseModel):
    item : Union[str, 'ComplexType']

class MapType(BaseModel):
    key : Union[str, 'ComplexType']
    item : Union[str, 'ComplexType']

class ComplexType(BaseModel):
    list : Union[ListType, None] = None
    map : Union[MapType, None] = None

class ParamDef(BaseModel):
    doc : str = None
    type : Union[str, 'ComplexType'] = None
    value : Union[Any, None] = None
    append : Union[Any, None] = None
    prepend : Union[Any, None] = None
    path_append : Union[Any, None] = Field(alias="path-append", default=None)
    path_prepend : Union[Any, None] = Field(alias="path-prepend", default=None)

