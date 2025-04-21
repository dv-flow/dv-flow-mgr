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
from .task_def import PassthroughE, ConsumesE
from .param import Param
from .task_node import TaskNode
from .task_node_leaf import TaskNodeLeaf
from .task_node_ctor import TaskNodeCtor

@dc.dataclass
class TaskNodeCtorWrapper(TaskNodeCtor):
    T : Any
    _count : int = 0

    def mkTaskNode(self, builder, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if params is None:
            raise Exception("params is None")

        node = TaskNodeLeaf(
            name=name, 
            srcdir=srcdir, 
            params=params, 
            task=self.T, 
            ctxt=None,
            needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
        if name is None:
            name = "%s_%d" % (self.name, self._count)
            self._count += 1

        if builder is not None:
            node.rundir = builder.get_rundir(name)
        else:
            node.rundir = [name]
        return node

    def mkTaskParams(self, params : Dict = None) -> Any:
        obj = self.paramT()

        # Apply user-specified params
        for key,value in params.items():
            if not hasattr(obj, key):
                raise Exception("Parameters class %s does not contain field %s" % (
                    str(type(obj)),
                    key))
            else:
                if isinstance(value, Param):
                    if value.append is not None:
                        ex_value = getattr(obj, key, [])
                        ex_value.extend(value.append)
                        setattr(obj, key, ex_value)
                    elif value.prepend is not None:
                        ex_value = getattr(obj, key, [])
                        value = value.copy()
                        value.extend(ex_value)
                        setattr(obj, key, value)
                        pass
                    else:
                        raise Exception("Unhandled value spec: %s" % str(value))
                else:
                    setattr(obj, key, value)
        return obj
    
def task(paramT,passthrough=PassthroughE.Unused,consumes=ConsumesE.All):
    """Decorator to wrap a task method as a TaskNodeCtor"""
    def wrapper(T):
        task_mname = T.__module__
        task_module = sys.modules[task_mname]
        ctor = TaskNodeCtorWrapper(
            name=T.__name__, 
            srcdir=os.path.dirname(os.path.abspath(task_module.__file__)), 
            paramT=paramT,
            passthrough=passthrough,
            consumes=consumes,
            needs=[],
            T=T)
        return ctor
    return wrapper

