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
class TaskVcsSimImage(VlTaskSimImage):

    def getRefTime(self):
        if os.path.isfile(os.path.join(self.rundir, 'simv')):
            return os.path.getmtime(os.path.join(self.rundir, 'simv'))
        else:
            raise Exception
    
    async def build(self, files : List[str], incdirs : List[str]):
        cmd = ['vcs', '-sverilog']

        for incdir in incdirs:
            cmd.append('+incdir+%s' % incdir)

        cmd.extend(files)

        if len(self.params.top):
            cmd.extend(['-top', "+".join(self.params.top)])

        proc = await self.session.create_subprocess(*cmd,
                                                        cwd=self.rundir)
        await proc.wait()

        if proc.returncode != 0:
            raise Exception("VCS simv failed")

class TaskVcsSimImageParams(VlTaskSimImageParams):
    pass

class TaskVcsSimImageMemento(VlTaskSimImageMemento):
    pass

class TaskVcsSimImageCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskVcsSimImageParams, TaskVcsSimImage)
