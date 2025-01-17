import os
import sys
import glob
import fnmatch
import importlib
import pydantic.dataclasses as dc
from ..package import TaskCtor
from ..task import Task, TaskParams, TaskCtorT
from ..task_data import TaskData
from ..task_memento import TaskMemento
from typing import List, Tuple
import dataclasses as dc
from ..package_def import Package

class TaskPyClass(Task):

    async def run(self, input : TaskData) -> TaskData:

        if self.srcdir not in sys.path:
            sys.path.insert(0, self.srcdir)

        print("sys.path: %s" % str(sys.path), flush=True)
        idx = self.params.pyclass.rfind('.')
        modname = self.params.pyclass[:idx]
        clsname = self.params.pyclass[idx+1:]

        if os.path.isfile(os.path.join(self.basedir, "my_module.py")):
            print("my_module.py exists", flush=True)
        else:
            print("my_module.py does not exist", flush=True)

        try:
            print("modname=%s" % modname, flush=True)
            module = importlib.import_module(modname)
        except ModuleNotFoundError as e:
            print("Module not found: %s syspath=%s" % (str(e), str(sys.path)), flush=True)
            raise e

        cls = getattr(module, clsname)

        obj = cls(self.name, self.task_id, self.session, self.basedir, srcdir=self.srcdir)

        return await obj.run(input)


class TaskPyClassParams(TaskParams):
    pyclass : str

class TaskPyClassMemento(TaskMemento):
    pass

class TaskPyClassCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskPyClassParams, TaskPyClass)

@dc.dataclass
class PackageBuiltin(Package):

    def __post_init__(self):
        print("PackageBuiltin::__post_init__", flush=True)
        self.tasks["PyClass"] = TaskPyClass()
