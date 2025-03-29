#****************************************************************************
#* task_node_ctor_def_base.py
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
import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_def import RundirE
from .task_node_ctor import TaskNodeCtor

@dc.dataclass
class TaskNodeCtorDefBase(TaskNodeCtor):
    """Task defines its own needs, that will need to be filled in"""
    needs : List['str']
    rundir : RundirE 

    def __post_init__(self):
        if self.needs is None:
            self.needs = []

    def getNeeds(self) -> List[str]:
        return self.needs

