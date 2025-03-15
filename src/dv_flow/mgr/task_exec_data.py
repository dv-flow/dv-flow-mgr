#****************************************************************************
#* task_exec_data.py
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
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List


class TaskExecData(BaseModel):
    """Data from a single exection of a task"""
    name : str
    start : str
    finish : str
    status : int
    memento : Any
    markers : List[Any]

class FlowExecData(BaseModel):
    """
    Data from multiple tasks executions. 'info' holds information
    across multiple flow invocations. 'tasks' holds the names of
    tasks executed in the most-recent invocation.
    """
    info : Dict[str, TaskExecData] = dc.Field(default_factory=dict)
    tasks : List[str] = dc.Field(default_factory=list)
