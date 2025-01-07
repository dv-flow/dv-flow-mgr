import os
import fnmatch
import pydantic.dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams
from ....task_data import TaskData
from ....task_memento import TaskMemento
from typing import List, Tuple

class TaskSimImage(Task):

    async def run(self, input : TaskData) -> TaskData:
        return input


