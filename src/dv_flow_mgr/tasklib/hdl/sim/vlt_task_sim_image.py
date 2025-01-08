import os
import fnmatch
import dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams, TaskCtorT
from ....task_data import TaskData
from ....task_memento import TaskMemento
from .vl_task_sim_image import VlTaskSimImage, VlTaskSimImageParams, VlTaskSimImageMemento
from typing import List, Tuple

from svdep import FileCollection, TaskCheckUpToDate, TaskBuildFileCollection

@dc.dataclass
class TaskVltSimImage(VlTaskSimImage):

    def getRefTime(self):
        if os.path.isdir(os.path.join(self.rundir, 'obj_dir/simv')):
            return os.path.getmtime(os.path.join(self.rundir, 'obj_dir/simv'))
        else:
            raise Exception
    
    async def build(self, files : List[str], incdirs : List[str]):
        cmd = ['verilator', '--binary', '-o', 'simv']

        for incdir in incdirs:
            cmd.append('+incdir+%s' % incdir)

        cmd.extend(files)

        for top in self.params.top:
            cmd.extend(['--top-module', top])

        print("self.basedir=%s" % self.rundir)
        proc = await self.session.create_subprocess(*cmd,
                                                        cwd=self.rundir)
        await proc.wait()

        if proc.returncode != 0:
            raise Exception("Verilator failed")

class TaskVltSimImageParams(VlTaskSimImageParams):
    pass

class TaskVltSimImageMemento(VlTaskSimImageMemento):
    pass

class TaskVltSimImageCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskVltSimImageParams, TaskVltSimImage)
