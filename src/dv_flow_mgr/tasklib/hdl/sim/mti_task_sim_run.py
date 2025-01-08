import os
import fnmatch
import pydantic.dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams, TaskCtorT
from ....task_data import TaskData
from ....task_memento import TaskMemento
from typing import List, Tuple

class TaskMtiSimRun(Task):

    async def run(self, input : TaskData) -> TaskData:
        vl_fileset = input.getFileSets("verilatorBinary")

        build_dir = vl_fileset[0].basedir

        cmd = [
            'vsim', '-batch', '-do', 'run -all; quit -f',
            '-work', os.path.join(build_dir, 'work'),
            'simv_opt'
        ]

        fp = open(os.path.join(self.rundir, 'sim.log'), "w")
        proc = await self.session.create_subprocess(*cmd,
                                                    cwd=self.rundir,
                                                    stdout=fp)

        await proc.wait()

        fp.close()

        output = TaskData()
        output.addFileSet(FileSet(src=self.name, type="simRunDir", basedir=self.rundir))

        return output

class TaskMtiSimRunParams(TaskParams):
    pass

class TaskMtiSimRunMemento(TaskMemento):
    pass

class TaskMtiSimRunCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskMtiSimRunParams, TaskMtiSimRun)

