import os
import fnmatch
import pydantic.dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams
from ....task_data import TaskData
from ....task_memento import TaskMemento
from typing import List, Tuple

class TaskVltSimRun(Task):

    async def run(self, input : TaskData) -> TaskData:
        print("run: %s: base=%s type=%s include=%s" % (
            self.name,
            self.params.base, self.params.type, str(self.params.include)
        ))

        glob_root = os.path.join(self.basedir, self.params.base)

        ex_memento = self.getMemento(TaskFileSetMemento)

        fs = FileSet(
            src=self.name, 
            type=self.params.type,
            basedir=glob_root)
        print("glob_root: %s" % glob_root)

        memento = TaskFileSetMemento()
        for root, _, files in os.walk(glob_root):
            for f in files:
                print("File: %s" % f)
                memento.files.append((f, os.path.getmtime(os.path.join(root, f))))

        # Check to see if the filelist or fileset have changed
        # Only bother doing this if the upstream task data has not changed
        if ex_memento is not None and not input.changed:
            ex_memento.files.sort(key=lambda x: x[0])
            memento.files.sort(key=lambda x: x[0])
            input.changed = ex_memento != memento
        else:
            input.changed = True

        self.setMemento(memento)

        input.addFileSet(fs)
        return input

class TaskVltSimImageParams(TaskParams):
    base : str = "${{ task.basedir }}"
    type : str = "Unknown"
    include : List[str] = dc.Field(default_factory=list)
    exclude : List[str] = dc.Field(default_factory=list)

class TaskVltSimImageMemento(TaskMemento):
    files : List[Tuple[str,float]] = dc.Field(default_factory=list)

class TaskVltSimRunCtor(TaskCtor):

    def mkTaskParams(self) -> TaskParams:
        return TaskVltSimImageParams()
    
    def setTaskParams(self, params : TaskParams, pvals : dict):
        for p in pvals.keys():
            if not hasattr(params, p):
                raise Exception("Unsupported parameter: " + p)
            else:
                setattr(params, p, pvals[p])

    def mkTask(self, name : str, task_id : int, session : 'Session', params : TaskParams, depends : List['Task']) -> 'Task':
        task = TaskVltSimRun(
            name=name, 
            task_id=task_id, 
            session=session, 
            params=params,
            basedir=os.path.dirname(os.path.abspath(__file__)),
            srcdir=os.path.dirname(os.path.abspath(__file__)))
        task.depends.extend(depends)
        return task
    
