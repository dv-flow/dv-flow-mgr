#****************************************************************************
#* task_node_ctor.py
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
from .task_node import TaskNode
from .param import Param

@dc.dataclass
class TaskNodeCtor(object):
    """
    Factory for a specific task type. A TaskNodeCtor has two clients. 
    - The graph builder may call it. In this case, 'needs', passthrough,
      and consumes are known. Also, the default parameters block is built
    - It may be called to programmatically create a task from a Python
      workflow (eg pytest-dv-flow). In this case, the API call may supply
      additional needs, specify passthrough and consumes requirements,
      and customize parameter values
    """
    name : str
    srcdir : str
    paramT : Any
    passthrough : bool
    consumes : List[Any]
    needs : List[str]

    def __post_init__(self):
        if self.paramT is None:
            raise Exception("paramT must be specified for TaskNodeCtor")

    def __call__(self, 
                 builder=None,
                 name=None,
                 srcdir=None,
                 params=None,
                 needs=None,
                 passthrough=None,
                 consumes=None,
                 **kwargs):
        """Convenience method for direct creation of tasks"""
        if params is None:
            params = self.mkTaskParams(kwargs)
        
        node = self.mkTaskNode(
            builder=builder,
            srcdir=srcdir, 
            params=params, 
            name=name, 
            needs=needs)
        if passthrough is not None:
            node.passthrough = passthrough
        else:
            node.passthrough = self.passthrough
        if consumes is not None:
            if node.consumes is None:
                node.consumes = consumes
            else:
                node.consumes.extend(consumes)
        else:
            if node.consumes is None:
                node.consumes = self.consumes

        return node

    def getNeeds(self) -> List[str]:
        return []

    def mkTaskNode(self,
                   builder,
                   params,
                   srcdir=None,
                   name=None,
                   needs=None) -> TaskNode:
        raise NotImplementedError("mkTaskNode in type %s" % str(type(self)))

    def mkTaskParams(self, params : Dict = None) -> Any:
        obj = self.paramT()

        # Apply user-specified params
        if params is not None:
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
