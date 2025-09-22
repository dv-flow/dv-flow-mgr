#****************************************************************************
#* task_gen_ctxt.py
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
import asyncio
import dataclasses as dc
import logging
from typing import Any, ClassVar, List
from .task_node import TaskNode

@dc.dataclass
class TaskGenInputData(object):
    params : Any

@dc.dataclass
class TaskGenCtxt(object):
    rundir : str
    srcdir : str
    input : TaskNode
    basename : str
    builder : 'TaskGraphBuilder'
    body : List['Task'] = dc.field(default_factory=list)
    tasks : List['TaskNode'] = dc.field(default_factory=list)
    _idx : int = 1
    _log : ClassVar[logging.Logger] = logging.getLogger("TaskGenCtxt")

    def mkTaskNode(self, type_t, name=None, srcdir=None, needs=None, **kwargs):
        """
        Creates a new task node.
        - type_t - type name of the task
        - name - (Optional) full name of the task
        - srcdir - (Optional) 
        - needs - (Optional) task nodes required by this task
        - kwargs - (Optionl) parameter overrides for the task
        """
        if name is None:
            name = self.mkName(name)

        return self.builder.mkTaskNode(
            type_t,
            name=name,
            srcdir=srcdir, 
            needs=needs, 
            **kwargs)
    
    def mkName(self, name : str) -> str:
        """
        Create a taskname relative to containing compound task
        """
        if name is None:
            name = "anon_%d" % self._idx
            self._idx += 1

        return (self.basename + "." + name)

    def addTask(self, task : 'TaskNode') -> TaskNode:
        """
        Add the specified task to the graph
        """
        if task is None:
            raise Exception("Task is None")
        self.tasks.append(task)
        return task

    # def marker(self, m):
    #     pass

    # def error(self, msg):
    #     pass

    def getInputs(self) -> List[object]:
        """Gets the input datasets of the containing task"""
        self._log.debug("--> getInputs")
        in_params = asyncio.run(self.input.get_in_params(self.builder.rundir))

        self._log.debug("<-- getInputs %d" % len(in_params))
        return in_params



