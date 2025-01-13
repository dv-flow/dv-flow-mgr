#****************************************************************************
#* task_def.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Union, Tuple
from .task import Task

@dc.dataclass
class TaskSpec(object):
    name : str


class TaskDef(BaseModel):
    """Holds definition information (ie the YAML view) for a task"""
    name : str
    type : Union[str,TaskSpec] = dc.Field(default_factory=list)
    depends : List[Union[str,TaskSpec]] = dc.Field(default_factory=list, alias="needs")
    params: Dict[str,Any] = dc.Field(default_factory=dict, alias="with")

    def copy(self) -> 'TaskDef':
        ret = TaskDef(
            name=self.name,
            type=self.type,
            depends=self.depends.copy())
        return ret  

