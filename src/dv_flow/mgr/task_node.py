#****************************************************************************
#* task_node.py
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
from .task_data import TaskDataOutput, TaskDataResult
from .param import Param

class RundirE(enum.Enum):
    Unique = enum.auto()
    Inherit = enum.auto()

@dc.dataclass
class TaskNode(object):
    """Executable view of a task"""
    # Ctor fields -- must specify on construction
    name : str
    srcdir : str
    # This can be the resolved parameters
    params : Any

    # Runtime fields -- these get populated during execution
    changed : bool = False
    passthrough : bool = False
    consumes : List[Any] = dc.field(default_factory=list)
    needs : List[Tuple['TaskNode',bool]] = dc.field(default_factory=list)
    rundir : str = dc.field(default=None)
    rundir_t : RundirE = dc.field(default=RundirE.Unique)
    output : TaskDataOutput = dc.field(default=None)
    result : TaskDataResult = dc.field(default=None)
    start : float = dc.field(default=None)
    end : float = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNode")

    def __post_init__(self):
        if self.needs is None:
            self.needs = []
        else:
            for i,need in enumerate(self.needs):
                if not isinstance(need, tuple):
                    self.needs[i] = (need, False)

    async def do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        pass

    def __hash__(self):
        return id(self)

    def _matches(self, params, consumes):
        """Determines if a parameter set matches a set of consumed parameters"""
        self._log.debug("--> _matches: %s params=%s consumes=%s" % (
            self.name, str(params), str(consumes)))
        consumed = False
        self._log.debug("params: %s" % str(params))
        for c in consumes:
            # All matching attribute keys must have same value
            match = False
            for k,v in c.items():
                self._log.debug("k,v: %s,%s - hasattr=%s" % (k,v, hasattr(params, k)))
                if hasattr(params, k):
                    self._log.debug("getattr=%s v=%s" % (getattr(params, k), v))
                    if getattr(params, k) == v:
                        match = True
                    else:
                        match = False
                        break
            self._log.debug("match: %s" % match)
            if match:
                consumed = True
                break
        self._log.debug("<-- _matches: %s %s" % (self.name, consumed))
        return consumed
    



