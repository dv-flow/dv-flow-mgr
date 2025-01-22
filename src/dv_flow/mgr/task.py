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
from typing import Any, Callable, Dict, List, Tuple
from .task_data import TaskData
from .task_memento import TaskMemento

@dc.dataclass
class TaskSpec(object):
    name : str

class TaskParams(BaseModel):
    pass

@dc.dataclass
class TaskCtor(object):
    task_ctor : Callable
    param_ctor : Callable
    params : Dict[str,Any] = None
    srcdir : str = None
    depends : List[TaskSpec] = dc.field(default_factory=list)

    def copy(self):
        return TaskCtor(
            task_ctor=self.task_ctor,
            param_ctor=self.param_ctor,
            params=self.params,
            srcdir=self.srcdir,
            depends=self.depends.copy())

    def mkParams(self):
        print("mkParams: %s" % str(self.params))
        ret = self.param_ctor()
        if self.params is not None:
            for k,v in self.params.items():
                setattr(ret, k, v)
        return ret

@dc.dataclass
class Task(object):
    """Executable view of a task"""
    name : str
    params : TaskParams
    srcdir : str = None
    session : 'TaskGraphRunner' = None
    basedir : str = None
    memento : TaskMemento = None
    depend_refs : List['TaskSpec'] = dc.field(default_factory=list)
    depends : List[int] = dc.field(default_factory=list)
    running : bool = False
    output_set : bool = False
    output : Any = None
    output_ev : Any = asyncio.Event()

    # Implementation data below
    basedir : str = dc.field(default=None)
    rundir : str = dc.field(default=None)
    impl : str = None
    body: Dict[str,Any] = dc.field(default_factory=dict)
    impl_t : Any = None

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
                    print("Failed to load memento %s: %s" % (
                        os.path.join(self.rundir, "memento.json"), str(e)))
                    os.unlink(os.path.join(self.rundir, "memento.json"))
        return self.memento

    def setMemento(self, memento : TaskMemento):
        self.memento = memento

    async def isUpToDate(self, memento) -> bool:
        return False

    async def do_run(self) -> TaskData:
        print("do_run: %s - %d depends" % (self.name, len(self.depends)))
        if len(self.depends) > 0:
            awaitables = [dep.waitOutput() for dep in self.depends]
            deps_o = await asyncio.gather(*awaitables)

            # Merge filesets. A fileset with the same
            print("deps_o: %s" % str(deps_o))


#            print("deps_m: %s" % str(deps_m))

            # Merge the output of the dependencies into a single input data
#            if len(self.depends) > 1:
#                raise Exception("TODO: handle >1 inputs")

            # Now that we have a clean input object, we need
            # to build the dep map

#            input = self.depends[0].output.copy()
            input = TaskData.merge(deps_o)
            input.src = self.name
            input.deps[self.name] = list(inp.name for inp in self.depends)
        else:
            input = TaskData()
        


        # Mark the source of this data as being this task
        input.src = self.name

        self.init_rundir()

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
        self.save_memento()

        self.running = False

        # Combine data from the deps to produce a result
        return result

    async def run(self, input : TaskData) -> TaskData:
        raise NotImplementedError("TaskImpl.run() not implemented")
    
    def init_rundir(self):
        if not os.path.isdir(self.rundir):
            os.makedirs(self.rundir)

    def save_memento(self):
        if self.memento is not None:
            with open(os.path.join(self.rundir, "memento.json"), "w") as fp:
                fp.write(self.memento.model_dump_json(indent=2))
    
    def setOutput(self, output : TaskData):
        self.output_set = True
        output.src = self.name
        self.output = output
        self.output_ev.set()

    async def waitOutput(self) -> TaskData:
        if not self.output_set:
            if self.running:
                # Task is already running
                print("wait")
                await self.output_ev.wait()
            else:
                self.running = True
                print("start task")
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
        



