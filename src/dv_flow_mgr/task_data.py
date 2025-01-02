#****************************************************************************
#* task_data.py
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
from typing import Any, Dict, List, Tuple
from .fileset import FileSet

class TaskData(BaseModel):
    task_id : int = -1
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    deps : List['TaskData'] = dc.Field(default_factory=list)
    changed : bool = False

    def clone(self) -> 'TaskData':
        ret = TaskData()
        ret.taskid = self.taskid
        ret.params = self.params.copy()
        for d in self.deps:
            ret.deps.append(d.clone())
        ret.changed = self.changed
        return ret




