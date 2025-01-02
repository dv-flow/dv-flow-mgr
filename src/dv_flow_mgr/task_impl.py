import asyncio
import dataclasses as dc
from .task import Task
from .task_data import TaskData
from typing import Any, Dict, List

@dc.dataclass
class TaskImpl(object):
    spec : Task
    session : 'Session'
    deps : List['TaskImpl'] = dc.field(default_factory=list)
    task_id : int = -1
    output_set : bool = False
    output : Any = None
    output_ev : Any = asyncio.Event()

    def addDep(self, dep : 'TaskImpl'):
        self.deps.append(dep)

    async def do_run(self) -> TaskData:
        self.task_id = self.session.mkTaskId(self.spec)
        awaitables = [dep.waitOutput() for dep in self.deps]

        deps_o = await asyncio.gather(*awaitables)

        # Get the 
        result = await self.run()

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

    async def run(self) -> TaskData:
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
    


