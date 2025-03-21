#****************************************************************************
#* task_node_ctor_task.py
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
from .task_params_ctor import TaskParamsCtor
from .param_ref_eval import ParamRefEval
from .param import Param
from .task_node import TaskNode
from .task_node_leaf import TaskNodeLeaf
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_def_base import TaskNodeCtorDefBase

@dc.dataclass
class TaskNodeCtorTask(TaskNodeCtorDefBase):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult']

    def mkTaskNode(self, builder, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNodeLeaf(
            name=name, 
            srcdir=srcdir, 
            params=params, 
            task=self.task,
            needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
        node.task = self.task

        return node
