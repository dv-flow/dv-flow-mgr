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
from .task_data import TaskData
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
        self._log.debug("--> %s::mkTask (%s)" % (self.name, str(self.task_ctor)))

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
        ret.srcdir = self.srcdir

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
    params : TaskParams
    srcdir : str = None
    session : 'TaskGraphRunner' = None
    basedir : str = None
    memento : TaskMemento = None
    depends : List['Task'] = dc.field(default_factory=list)
    output : Any = None

    # Implementation data below
    basedir : str = dc.field(default=None)
    rundir : str = dc.field(default=None)
    impl : str = None
    body: Dict[str,Any] = dc.field(default_factory=dict)
    impl_t : Any = None

    _log : ClassVar = logging.getLogger("Task")

    def init(self, runner, basedir):
        self.session = runner
        self.basedir = basedir

    def getMemento(self, T) -> TaskMemento:
        if os.path.isfile(os.path.join(self.rundir, "memento.json")):
            with open(os.path.join(self.rundir, "memento.json"), "r") as fp:
                try:
                    data = json.load(fp)
                    self.memento = T(**data)
                except Exception as e:
                    self._log.critical("Failed to load memento %s: %s" % (
                        os.path.join(self.rundir, "memento.json"), str(e)))
                    os.unlink(os.path.join(self.rundir, "memento.json"))
        return self.memento

    def setMemento(self, memento : TaskMemento):
        self.memento = memento

    async def isUpToDate(self, memento) -> bool:
        return False

    async def do_run(self, session) -> TaskData:
        self._log.info("--> %s (%s) do_run - %d depends" % (
            self.name, 
            str(type(self)),
            len(self.depends)))

        self.session = session

        if len(self.depends) > 0:
            deps_o = []
            for d in self.depends:
                dep_o = d.getOutput()
                if dep_o is None:
                    raise Exception("Null output for %s" % d.name)
                deps_o.append(dep_o)

            input = TaskData.merge(deps_o)
            input.src = self.name
            input.deps[self.name] = list(inp.name for inp in self.depends)
        else:
            input = TaskData()


        # Mark the source of this data as being this task
        input.src = self.name

        self.init_rundir()

        self.output = await self.run(input)

        if self.output is None:
            raise Exception("No output produced by %s" % self.name)
            result = TaskData()

        # Write-back the memento, if specified
        self.save_memento()

        # Combine data from the deps to produce a result
        self._log.info("<-- %s (%s) do_run - %d depends" % (
            self.name, 
            str(type(self)),
            len(self.depends)))
        return self.output

    async def run(self, input : TaskData) -> TaskData:
        raise NotImplementedError("TaskImpl.run() not implemented")
    
    def init_rundir(self):
        if not os.path.isdir(self.rundir):
            os.makedirs(self.rundir)

    def save_memento(self):
        if self.memento is not None:
            with open(os.path.join(self.rundir, "memento.json"), "w") as fp:
                fp.write(self.memento.model_dump_json(indent=2))
    
    def getOutput(self) -> TaskData:
        return self.output

    def getField(self, name : str) -> Any:
        if name in self.__dict__.keys():
            return self.__dict__[name]
        elif name in self.__pydantic_extra__.keys():
            return self.__pydantic_extra__[name]
        else:
            raise Exception("No such field %s" % name)
        



