#****************************************************************************
#* type_def.py
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
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field
from .param_def import ParamDef
from .srcinfo import SrcInfo

class TypeDef(BaseModel):
    name : str = Field(
        description="Name of the data type")
    uses : str = Field(
        default=None,
        description="Base type to inherit from. Supports type extension/specialization")
    doc : str = Field(
        default=None,
        description="Documentation for this type definition")
    params : Dict[str, Union[str, ParamDef]] = Field(
        alias="with", 
        default_factory=dict,
        description="Parameters for this type. Can be simple values or full parameter definitions")
    tags : List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Tags as type references with optional parameter overrides")
    srcinfo : SrcInfo = None
