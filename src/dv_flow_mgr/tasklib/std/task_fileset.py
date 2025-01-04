import pydantic.dataclasses as dc
from ...package import TaskCtor
from ...task import Task
from ...task_data import TaskData
from typing import List

class TaskFileSet(Task):
    base : str
    include : List[str] = dc.Field(default_factory=list)
    exclude : List[str] = dc.Field(default_factory=list)

    async def run(self, input : TaskData) -> TaskData:
        pass


class TaskFileSetCtor(TaskCtor):
    _supported_params = ("base", "include", "exclude")

    def mkTask(self, name : str, task_id : int, session : 'Session', params : dict, depends : List['Task']) -> 'Task':
        for p in params.keys():
            if p not in self._supported_params:
                raise Exception("Unsupported parameter: " + p)
        
        task = TaskFileSet(name=name, task_id=task_id, session=session, **params)

        task.depends.extend(depends)

        return task
    
    def mkTaskParams(self, params : dict) -> dict:
        return params
