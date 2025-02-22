#****************************************************************************
#* task.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
from .task_data import TaskData, TaskDataInput, TaskDataOutput, TaskDataResult
from .task_memento import TaskMemento

@dc.dataclass
class TaskSpec(object):
    name : str

class TaskParams(BaseModel):
    pass


@dc.dataclass
class TaskCtor(object):
    name : str
    uses : 'TaskCtor' = None
    srcdir : str = None
    depends : List[TaskSpec] = dc.field(default_factory=list)

    _log : ClassVar = logging.getLogger("TaskCtor")

    def mkTask(self, name : str, depends, rundir, srcdir=None, params=None):
        if srcdir is None:
            srcdir = self.srcdir
        if params is None:
            params = self.mkParams()

        if self.uses is not None:
            return self.uses.mkTask(name, depends, rundir, srcdir, params)
        else:
            raise NotImplementedError("TaskCtor.mkTask() not implemented for %s" % str(type(self)))
    
    def mkParams(self):
        self._log.debug("--> %s::mkParams" % self.name)
        if self.uses is not None:
            params = self.uses.mkParams()
        else:
            params = TaskParams()
        self._log.debug("<-- %s::mkParams: %s" % (self.name, str(params)))

        return params

    def applyParams(self, params):
        if self.uses is not None:
            self.uses.applyParams(params)


@dc.dataclass
class TaskCtorParam(TaskCtor):
    params : Dict[str,Any] = dc.field(default_factory=dict)

    _log : ClassVar = logging.getLogger("TaskCtorParam")

    def mkTask(self, name : str, depends, rundir, srcdir=None, params=None):
        self._log.debug("--> %s::mkTask" % self.name)
        if params is None:
            params = self.mkParams()
        if srcdir is None:
            srcdir = self.srcdir

        ret = self.uses.mkTask(name, depends, rundir, srcdir, params)

        self.applyParams(ret.params)
        self._log.debug("<-- %s::mkTask" % self.name)

        return ret

    def applyParams(self, params):
        self._log.debug("--> %s::applyParams: %s %s" % (self.name, str(type(self.params)), str(type(params))))
        if self.params is not None:
            for k,v in self.params.items():
                self._log.debug("  change %s %s=>%s" % (
                    k, 
                    str(getattr(params, k)),
                    str(v)))
                setattr(params, k, v)
        else:
            self._log.debug("  no params")
        self._log.debug("<-- %s::applyParams: %s" % (self.name, str(self.params)))

@dc.dataclass
class TaskCtorParamCls(TaskCtor):
    params_ctor : Callable = None

    _log : ClassVar = logging.getLogger("TaskCtorParamType")

    def mkParams(self):
        self._log.debug("--> %s::mkParams" % str(self.name))
        params = self.params_ctor()
        self._log.debug("<-- %s::mkParams: %s" % (str(self.name), str(type(params))))
        return params

@dc.dataclass
class TaskCtorCls(TaskCtor):
    task_ctor : Callable = None

    _log : ClassVar = logging.getLogger("TaskCtorCls")

    def mkTask(self, name : str, depends, rundir, srcdir=None, params=None):
        self._log.debug("--> %s::mkTask (%s) srcdir=%s" % (self.name, str(self.task_ctor), srcdir))

        if srcdir is None:
            srcdir = self.srcdir

        if params is None:
            params = self.mkParams()

        ret = self.task_ctor(
            name=name, 
            depends=depends, 
            rundir=rundir, 
            srcdir=srcdir, 
            params=params)

        # Update parameters on the way back
        self.applyParams(ret.params)

        self._log.debug("<-- %s::mkTask" % self.name)
        return ret

@dc.dataclass
class TaskCtorProxy(TaskCtor):
    task_ctor : TaskCtor = None
    param_ctor : Callable = None

    _log : ClassVar = logging.getLogger("TaskCtorProxy")

    def mkTask(self, *args, **kwargs):
        self._log.debug("--> %s::mkTask" % self.name)
        ret = self.task_ctor.mkTask(*args, **kwargs)
        self._log.debug("<-- %s::mkTask" % self.name)
        return ret

    def mkParams(self, params=None):
        self._log.debug("--> %s::mkParams: %s" % (self.name, str(self.params)))

        if params is None and self.param_ctor is not None:
            params = self.param_ctor()

        params = self.task_ctor.mkParams(params)

        if self.params is not None:
            for k,v in self.params.items():
                self._log.debug("  change %s %s=>%s" % (
                    k, 
                    str(getattr(params, k)),
                    str(v)))
                setattr(params, k, v)
        self._log.debug("<-- %s::mkParams: %s" % (self.name, str(self.params)))
        return params


@dc.dataclass
class Task(object):
    """Executable view of a task"""
    name : str

    # Need TaskDef 

    params : TaskParams # Might need to be set of instructions for building...
    # This needs to be 'inside out' -- listed bottom to top
    srcdir : str = dc.field(default=None)
    rundir : str = dc.field(default=None)
    depends    : List['Task'] = dc.field(default_factory=list)
    dependents : List['Task'] = dc.field(default_factory=list)
    output : TaskDataOutput = dc.field(default=None)

    _log : ClassVar = logging.getLogger("Task")

    async def run(self, 
                  input : TaskDataInput,
                  runner : 'TaskGraphRunner') -> TaskDataResult:
        raise NotImplementedError("TaskImpl.run() not implemented")

