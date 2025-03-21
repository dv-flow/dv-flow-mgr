#****************************************************************************
#* task_node_compound.py
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
import dataclasses as dc
from .task_node import TaskNode
from .task_node_leaf import TaskNodeLeaf
from .task_data import TaskDataResult, TaskDataInput, TaskDataOutput
from .task_runner import TaskRunner
from typing import Any, List

@dc.dataclass
class TaskNodeCompound(TaskNode):
    """A Compound task node is the 'out' node in the subgraph"""
    tasks : List[TaskNode] = dc.field(default_factory=list)
    input : TaskNode = None

    def __post_init__(self):
        self.input = TaskNodeLeaf(
            self.name + ".in",
            srcdir=self.srcdir,
            params=None)
        return super().__post_init__()

    async def do_run(self, 
                     runner : TaskRunner, 
                     rundir, 
                     memento : Any=None) -> TaskDataResult:
        pass

    def __hash__(self):
        return id(self)