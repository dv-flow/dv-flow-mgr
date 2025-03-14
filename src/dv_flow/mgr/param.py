#****************************************************************************
#* param.py
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
from pydantic import BaseModel
import pydantic.dataclasses as pdc
from typing import Any, List, Union

class ParamMeta(type):
    def __getitem__(self, T):
        ret = Union[T, Param]
        return ret

class ParamT(metaclass=ParamMeta):
    pass

class Param(BaseModel):
    append : Union[Any,List] = pdc.Field(default=None)
    prepend : Union[Any,List] = pdc.Field(default=None)
    append_path : Union[Any,List] = pdc.Field(default=None, alias="append-path")
    prepend_path : Union[Any,List] = pdc.Field(default=None, alias="prepend-path")


