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
import json
import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node_ctxt import TaskNodeCtxt
from .task_run_ctxt import TaskRunCtxt
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
    ctxt : TaskNodeCtxt

    # Runtime fields -- these get populated during execution
    changed : bool = False
    passthrough : bool = False
    consumes : List[Any] = dc.field(default_factory=list)
    needs : List[Tuple['TaskNode',bool]] = dc.field(default_factory=list)
    rundir : List[str] = dc.field(default=None)
    output : TaskDataOutput = dc.field(default=None)
    result : TaskDataResult = dc.field(default=None)
    start : float = dc.field(default=None)
    end : float = dc.field(default=None)
    save_exec_data : bool = dc.field(default=True)
    iff : bool = dc.field(default=True)
    parent : 'TaskNode' = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNode")

    def __post_init__(self):
        # Give this a default run directory based on the task name
        self.rundir = [self.name]
        if self.needs is None:
            self.needs = []
        else:
            for i,need in enumerate(self.needs):
                if not isinstance(need, tuple):
                    self.needs[i] = (need, False)

    @property
    def first(self):
        return self

    async def do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        raise NotImplementedError("do_run not implemented for %s" % self.__class__.__name__)

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
                    self._log.debug("getattr=\"%s\" v=\"%s\"" % (getattr(params, k), v))
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
    
    def _save_exec_data(self, rundir, ctxt : TaskRunCtxt, input : TaskDataInput):
        """Saves execution data to the rundir"""
        data = {
            "name": self.name,
            "srcdir": self.srcdir,
            "rundir": rundir,
            "input": input.model_dump(warnings=False),
            "needs": [need[0].name for need in self.needs],
            "commands": [cmd.model_dump() for cmd in ctxt._exec_info],
            "result": {
                "status": self.result.status,
                "changed": self.result.changed,
                "memento": self.result.memento.model_dump() if self.result.memento else None,
            },
            "output": self.output.model_dump(),
        }

        if isinstance(self.consumes, list):
            data["consumes"] = self.consumes
        else:
            data["consumes"] = str(self.consumes)

        if isinstance(self.passthrough, list):
            data["passthrough"] = self.passthrough
        else:
            data["passthrough"] = str(self.passthrough)

        with open(os.path.join(rundir, "%s.exec_data.json" % self.name), "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    



