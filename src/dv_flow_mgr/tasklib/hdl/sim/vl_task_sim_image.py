import os
import fnmatch
import dataclasses
import shutil
import pydantic.dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams, TaskCtorT
from ....task_data import TaskData
from ....task_memento import TaskMemento
from typing import List, Tuple

from svdep import FileCollection, TaskCheckUpToDate, TaskBuildFileCollection

class VlTaskSimImage(Task):

    def getRefTime(self):
        raise NotImplementedError()

    async def build(self, files : List[str], incdirs : List[str]):
        raise NotImplementedError()

    async def run(self, input : TaskData) -> TaskData:
        ex_memento = self.getMemento(VlTaskSimImageMemento)
        in_changed = (ex_memento is None)

        for dep in input.deps:
            in_changed |= dep.changed

        files = []
        incdirs = []
        memento = ex_memento

        vl_filesets = input.getFileSets(("verilogSource", "systemVerilogSource"))
        for file in vl_filesets[0].files:
            files.append(os.path.join(vl_filesets[0].basedir, file))

        if not in_changed:
            try:
                ref_mtime = self.getRefTime()
                info = FileCollection.from_dict(ex_memento.svdeps)
                in_changed = not TaskCheckUpToDate(files, incdirs).check(info, ref_mtime)
            except Exception as e:
                print("Unexpected output-directory format. Rebuilding")
                shutil.rmtree(self.rundir)
                os.makedirs(self.rundir)
                in_changed = True

        if in_changed:
            memento = VlTaskSimImageMemento()

            # First, create dependency information
            info = TaskBuildFileCollection(files, incdirs).build()
            memento.svdeps = info.to_dict()

            await self.build(files, incdirs) 

        output = TaskData()
        output.addFileSet(FileSet(src=self.name, type="verilatorBinary", basedir=self.rundir))
        output.changed = in_changed

        self.setMemento(memento)
        return output


class VlTaskSimImageParams(TaskParams):
    debug : bool = False
    top : List[str] = dc.Field(default_factory=list)

class VlTaskSimImageMemento(TaskMemento):
    svdeps : dict = dc.Field(default_factory=dict)

