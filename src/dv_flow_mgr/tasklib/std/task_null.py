import os
import glob
import fnmatch
import pydantic.dataclasses as dc
from ...package import TaskCtor
from ...task import Task, TaskParams, TaskCtorT
from ...task_data import TaskData
from ...task_memento import TaskMemento
from typing import List, Tuple

class TaskNull(Task):

    async def run(self, input : TaskData) -> TaskData:
        # No memento ; data pass-through
        return input

class TaskNullParams(TaskParams):
    pass

class TaskNullMemento(TaskMemento):
    pass

class TaskNullCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskNullParams, TaskNull)
    
