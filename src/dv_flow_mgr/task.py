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
import asyncio
import dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Tuple
from .task_data import TaskData
from .task_memento import TaskMemento

@dc.dataclass
class TaskSpec(object):
    name : str

@dc.dataclass
class Task(object):
    """Executable view of a task"""
    name : str
    task_id : int
    session : 'Session'
    depend_refs : List['TaskSpec'] = dc.field(default_factory=list)
    depends : List[int] = dc.field(default_factory=list)
    output_set : bool = False
    output : Any = None
    output_ev : Any = asyncio.Event()

    # Implementation data below
    basedir : str = dc.field(default=None)
    impl : str = None
    body: Dict[str,Any] = dc.field(default_factory=dict)
    impl_t : Any = None

    async def do_run(self) -> TaskData:
        if len(self.depends) > 0:
            awaitables = [dep.waitOutput() for dep in self.depends]
            deps_o = await asyncio.gather(*awaitables)

            # Merge the output of the dependencies into a single input data
            input = None
        else:
            input = TaskData()

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
        



