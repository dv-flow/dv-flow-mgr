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
import asyncio
import dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Tuple
from .task_data import TaskData
from .task_memento import TaskMemento

@dc.dataclass
class TaskSpec(object):
    name : str

class TaskParams(BaseModel):
    pass

class TaskCtor(object):
    def mkTaskParams(self) -> TaskParams:
        raise NotImplementedError()
    
    def setTaskParams(self, params : TaskParams, pvals : Dict[str,Any]):
        raise NotImplementedError()         

    def mkTask(self, name : str, task_id : int, session : 'Session', params : TaskParams, depends : List['Task']) -> 'Task':
        raise NotImplementedError()         

@dc.dataclass
class TaskParamCtor(object):
    base : TaskCtor
    params : Dict[str,Any]
    basedir : str

    def mkTaskParams(self) -> TaskParams:
        params = self.base.mkTaskParams()
        self.base.setTaskParams(params, self.params)
        return params
    
    def setTaskParams(self, params : Dict, pvals : Dict[str,Any]):
        pass

    def mkTask(self, name : str, task_id : int, session : 'Session', params : Dict, depends : List['Task']) -> 'Task':
        task =  self.base.mkTask(
            name=name, 
            task_id=task_id, 
            session=session, 
            params=params, 
            depends=depends)
        task.basedir = self.basedir
        return task

@dc.dataclass
class PackageTaskCtor(TaskCtor):
    name : str
    pkg : 'Package'

    def mkTaskParams(self, params : Dict) -> Dict:
        return self.pkg.mkTaskParams(self.name, params)
    def mkTask(self, name : str, task_id : int, session : 'Session', params : Dict, depends : List['Task']) -> 'Task':
        return self.pkg.mkTask(self.name, task_id, session, params, depends)

@dc.dataclass
class Task(object):
    """Executable view of a task"""
    name : str
    task_id : int
    session : 'Session'
    params : TaskParams
    basedir : str
    srcdir : str = None
    memento : TaskMemento = None
    depend_refs : List['TaskSpec'] = dc.field(default_factory=list)
    depends : List[int] = dc.field(default_factory=list)
    output_set : bool = False
    output : Any = None
    output_ev : Any = asyncio.Event()

    # Implementation data below
    basedir : str = dc.field(default=None)
    rundir : str = dc.field(default=None)
    impl : str = None
    body: Dict[str,Any] = dc.field(default_factory=dict)
    impl_t : Any = None

    def getMemento(self, T) -> TaskMemento:
        if os.path.isfile(os.path.join(self.rundir, "memento.json")):
            with open(os.path.join(self.rundir, "memento.json"), "r") as fp:
                try:
                    data = json.load(fp)
                    self.memento = T(**data)
                except Exception as e:
                    print("Failed to load memento %s: %s" % (
                        os.path.join(self.rundir, "memento.json"), str(e)))
                    os.unlink(os.path.join(self.rundir, "memento.json"))
        return self.memento

    def setMemento(self, memento : TaskMemento):
        self.memento = memento

    async def do_run(self) -> TaskData:
        if len(self.depends) > 0:
            awaitables = [dep.waitOutput() for dep in self.depends]
            deps_o = await asyncio.gather(*awaitables)

            # Merge the output of the dependencies into a single input data
            input = None
        else:
            input = TaskData()

        if not os.path.isdir(self.rundir):
            os.makedirs(self.rundir)

        result = await self.run(input)

        if not self.output_set:
            if result is None:
                result = TaskData()

            # We perform an auto-merge algorithm if the task 
            # doesn't take control
#            for dep_o in deps_o:
#                result.deps.append(dep_o.clone())

            self.setOutput(result)
        else:
            # The task has taken control of the output
            result = self.getOutput()

        # Write-back the memento, if specified
        if self.memento is not None:
            with open(os.path.join(self.rundir, "memento.json"), "w") as fp:
                fp.write(self.memento.model_dump_json(indent=2))

        # Combine data from the deps to produce a result
        return result

    async def run(self, input : TaskData) -> TaskData:
        raise NotImplementedError("TaskImpl.run() not implemented")
    
    def setOutput(self, output : TaskData):
        self.output_set = True
        output.task_id = self.task_id
        self.output = output
        self.output_ev.set()

    async def waitOutput(self) -> TaskData:
        if not self.output_set:
            if self.task_id != -1:
                # Task is already running
                await self.output_ev.wait()
            else:
                self.task_id = 0
                await self.do_run()
        return self.output
    
    def getOutput(self) -> TaskData:
        return self.output

    def getField(self, name : str) -> Any:
        if name in self.__dict__.keys():
            return self.__dict__[name]
        elif name in self.__pydantic_extra__.keys():
            return self.__pydantic_extra__[name]
        else:
            raise Exception("No such field %s" % name)
        



