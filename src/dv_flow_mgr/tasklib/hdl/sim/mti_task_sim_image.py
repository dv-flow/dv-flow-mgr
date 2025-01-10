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
class TaskMtiSimImage(VlTaskSimImage):

    def getRefTime(self):
        if os.path.isfile(os.path.join(self.rundir, 'work.d')):
            return os.path.getmtime(os.path.join(self.rundir, 'work.d'))
        else:
            raise Exception("work.d not found (%s)")
    
    async def build(self, files : List[str], incdirs : List[str]):
        if not os.path.isdir(os.path.join(self.rundir, 'work')):
            cmd = ['vlib', 'work']
            proc = await self.session.create_subprocess(*cmd,
                                                        cwd=self.rundir)
            await proc.wait()
            if proc.returncode != 0:
                raise Exception("Questa vlib failed")

        cmd = ['vlog', '-sv']

        for incdir in incdirs:
            cmd.append('+incdir+%s' % incdir)

        cmd.extend(files)

        proc = await self.session.create_subprocess(*cmd,
                                                        cwd=self.rundir)
        await proc.wait()
        if proc.returncode != 0:
            raise Exception("Questa compile failed")

        cmd = ['vopt', '-o', 'simv_opt']

        for top in self.params.top:
            cmd.append(top)

        proc = await self.session.create_subprocess(*cmd,
                                                        cwd=self.rundir)

        await proc.wait()

        with open(os.path.join(self.rundir, 'work.d'), "w") as fp:
            fp.write("\n")

        if proc.returncode != 0:
            raise Exception("Questa opt failed")

class TaskMtiSimImageParams(VlTaskSimImageParams):
    pass

class TaskMtiSimImageMemento(VlTaskSimImageMemento):
    pass

class TaskMtiSimImageCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskMtiSimImageParams, TaskMtiSimImage)
