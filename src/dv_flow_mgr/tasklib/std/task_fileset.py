import os
import glob
import fnmatch
import pydantic.dataclasses as dc
from ...fileset import FileSet
from ...package import TaskCtor
from ...task import Task, TaskParams
from ...task_data import TaskData
from ...task_memento import TaskMemento
from typing import List, Tuple

class TaskFileSet(Task):

    async def run(self, input : TaskData) -> TaskData:
        print("TaskFileSet run: %s: basedir=%s, base=%s type=%s include=%s" % (
            self.name,
            self.basedir,
            self.params.base, self.params.type, str(self.params.include)
        ))

        glob_root = os.path.join(self.basedir, self.params.base)

        ex_memento = self.getMemento(TaskFileSetMemento)

        fs = FileSet(
            src=self.name, 
            type=self.params.type,
            basedir=glob_root)
        print("glob_root: %s" % glob_root)

        if not isinstance(self.params.include, list):
            self.params.include = [self.params.include]

        included_files = []
        for pattern in self.params.include:
            print("pattern: %s" % pattern)
            included_files.extend(glob.glob(os.path.join(glob_root, pattern), recursive=False))

        memento = TaskFileSetMemento()
        for file in included_files:
            if not any(glob.fnmatch.fnmatch(file, os.path.join(glob_root, pattern)) for pattern in self.params.exclude):
                memento.files.append((file, os.path.getmtime(os.path.join(glob_root, file))))
                fs.files.append(file[len(glob_root):])

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

class TaskFileSetParams(TaskParams):
    base : str = ""
    type : str = "Unknown"
    include : List[str] = dc.Field(default_factory=list)
    exclude : List[str] = dc.Field(default_factory=list)

class TaskFileSetMemento(TaskMemento):
    files : List[Tuple[str,float]] = dc.Field(default_factory=list)

class TaskFileSetCtor(TaskCtor):

    def mkTaskParams(self) -> TaskParams:
        return TaskFileSetParams()
    
    def setTaskParams(self, params : TaskParams, pvals : dict):
        for p in pvals.keys():
            if not hasattr(params, p):
                raise Exception("Unsupported parameter: " + p)
            else:
                setattr(params, p, pvals[p])

    def mkTask(self, name : str, task_id : int, session : 'Session', params : TaskParams, depends : List['Task']) -> 'Task':
        task = TaskFileSet(
            name=name, 
            task_id=task_id, 
            session=session, 
            params=params,
            basedir=os.path.dirname(os.path.abspath(__file__)),
            srcdir=os.path.dirname(os.path.abspath(__file__)))
        task.depends.extend(depends)
        return task
    
