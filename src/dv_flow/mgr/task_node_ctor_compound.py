#****************************************************************************
#* task_node_ctor_compound.py
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
import os
import json
import dataclasses as dc
import logging
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_def import TaskDef
from .task_data import TaskDataOutput, TaskDataResult
from .task_node import TaskNode
from .task_node_ctor import TaskNodeCtor
from .task_node_compound import TaskNodeCompound

# TaskParamsCtor accepts an evaluation context and returns a task parameter object
TaskParamsCtor = Callable[[object], Any]

@dc.dataclass
class TaskNodeCtorCompound(TaskNodeCtor):
    task_def : TaskDef

    _log : ClassVar = logging.getLogger("TaskCtor")

    def mkTask(self, builder, params, srcdir=None, name=None, needs=None) -> 'TaskNode':
        """Creates a task object without a base task"""
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNodeCompound(name=name, srcdir=srcdir)

        self._buildSubGraph(node, None)

        if self.uses is not None:
            return self.uses.mkTask(name, srcdir)
        else:
            raise NotImplementedError("TaskCtor.mkTask() not implemented for %s" % str(type(self)))
    
    def _buildSubGraph(self, node):
        # Build out this task level, possibly
        pass
