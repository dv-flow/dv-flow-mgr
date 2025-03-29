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
from .task_node import TaskNode
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_def_base import TaskNodeCtorDefBase

@dc.dataclass
class TaskNodeCtorProxy(TaskNodeCtorDefBase):
    """Task has a 'uses' clause, so we delegate creation of the node"""
    uses : TaskNodeCtor

    def mkTaskNode(self, builder, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if srcdir is None:
            srcdir = self.srcdir
        builder.enter_uses()
        node = self.uses.mkTaskNode(
            builder=builder, params=params, srcdir=srcdir, name=name, needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
        builder.leave_uses()

        if not builder.in_uses():
            builder.addTask(name, node)
        return node
    
