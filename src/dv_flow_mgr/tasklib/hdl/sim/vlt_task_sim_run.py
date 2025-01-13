import os
import fnmatch
import pydantic.dataclasses as dc
from ....fileset import FileSet
from ....package import TaskCtor
from ....task import Task, TaskParams, TaskCtorT
from ....task_data import TaskData
from ....task_memento import TaskMemento
from typing import List, Tuple

class TaskVltSimRun(Task):

    async def run(self, input : TaskData) -> TaskData:
        vl_fileset = input.getFileSets("simDir")

        build_dir = vl_fileset[0].basedir

        cmd = [
            os.path.join(build_dir, 'obj_dir/simv'),
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

class TaskVltSimRunParams(TaskParams):
    pass

class TaskVltSimRunMemento(TaskMemento):
    pass

class TaskVltSimRunCtor(TaskCtorT):
    def __init__(self):
        super().__init__(TaskVltSimRunParams, TaskVltSimRun)

