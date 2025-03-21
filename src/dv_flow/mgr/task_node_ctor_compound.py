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
    tasks : List[TaskNodeCtor] = dc.field(default_factory=list)

    _log : ClassVar = logging.getLogger("TaskNodeCtorCompound")

    def mkTaskNode(self, builder, params, srcdir=None, name=None, needs=None) -> 'TaskNode':
        """Creates a task object without a base task"""
        self._log.debug("--> mkTaskNode %s (%d)" % (name, len(self.tasks)))
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNodeCompound(
            name=name, 
            srcdir=srcdir,
            params=params)

        builder.enter_compound(node)
        builder.addTask("in", node.input)

        self._buildSubGraph(builder, node)

        builder.leave_compound(node)

        self._log.debug("<-- mkTaskNode %s (%d)" % (name, len(node.needs)))
        return node

    def _buildSubGraph(self, builder, node):
        nodes = []

        for t in self.tasks:
            # Need to get the parent name
            needs = []
            for n in t.needs:
                need_name = "%s.%s" % (builder.package().name, n)
                task = builder.findTask(need_name)
                if task is None:
                    raise Exception("Failed to find task %s" % need_name)
                needs.append(task)
            sn = t.mkTaskNode(
                builder=builder, 
                params=t.mkTaskParams(),
                name=t.name,
                needs=needs)
            nodes.append(sn)
            builder.addTask(t.name, sn)

        
        for n in nodes:
            # All nodes 'need' the input node
            n.needs.append([builder.findTask("in"), False])
            node.needs.append([n, False])
        
        self._log.debug("nodes: %d (%d %d)" % (len(nodes), len(self.tasks), len(node.needs)))

        pass
