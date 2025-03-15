#****************************************************************************
#* task_impl_data.py
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
from typing import Any, ClassVar, Dict, Set, List, Tuple

class TaskImplParams(BaseModel):
    pass

class TaskImplSourceData(BaseModel):
    params : Any
    changed : bool
    memento : Any

class TaskImplResultData(BaseModel):
    data : List[Any]
    changed : bool
    memento : Any

