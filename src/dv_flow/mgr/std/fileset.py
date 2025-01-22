
import os
import fnmatch
import glob
import pydantic.dataclasses as dc
from typing import List, Tuple
from dv_flow.mgr import Task, TaskData, TaskMemento
from dv_flow.mgr import FileSet as _FileSet

class TaskFileSetMemento(TaskMemento):
    files : List[Tuple[str,float]] = dc.Field(default_factory=list)

class FileSet(Task):

    async def run(self, input : TaskData) -> TaskData:
        print("TaskFileSet run: %s: basedir=%s, base=%s type=%s include=%s" % (
            self.name,
            self.srcdir,
            self.params.base, self.params.type, str(self.params.include)
        ))


        ex_memento = self.getMemento(TaskFileSetMemento)
        memento = TaskFileSetMemento()

        if self.params is not None:
            glob_root = os.path.join(self.srcdir, self.params.base)

            print("glob_root: %s" % glob_root)

            fs = _FileSet(
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

            for file in included_files:
                if not any(glob.fnmatch.fnmatch(file, os.path.join(glob_root, pattern)) for pattern in self.params.exclude):
                    memento.files.append((file, os.path.getmtime(os.path.join(glob_root, file))))
                    fs.files.append(file[len(glob_root)+1:])

        # Check to see if the filelist or fileset have changed
        # Only bother doing this if the upstream task data has not changed
        if ex_memento is not None and not input.changed:
            ex_memento.files.sort(key=lambda x: x[0])
            memento.files.sort(key=lambda x: x[0])
            print("ex_memento.files: %s" % str(ex_memento.files))
            print("memento.files: %s" % str(memento.files))
            input.changed = ex_memento != memento
        else:
            input.changed = True

        self.setMemento(memento)

        if fs is not None:
            input.addFileSet(fs)

        return input

    pass
