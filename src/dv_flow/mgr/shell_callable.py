import asyncio
import dataclasses as dc
import logging
import os
from typing import ClassVar, List
from .task_data import TaskDataResult

@dc.dataclass
class ShellCallable(object):
    body : str
    shell : str
    _log : ClassVar = logging.getLogger("ShellCallable")

    async def __call__(self, ctxt, input):

        shell = ("/bin/%s" % self.shell) if self.shell != "shell" else "/bin/sh"
        # Setup environment for the call
        env = ctxt.env.copy()
        env["TASK_SRCDIR"] = input.srcdir
        env["TASK_RUNDIR"] = input.rundir
#        env["TASK_PARAMS"] = input.params.dumpto_json()
        fp = open(os.path.join(input.rundir, "%s.log" % input.name), "w")

        proc = await asyncio.create_subprocess_shell(
            self.body,
            shell=self.shell,
            env=env,
            cwd=input.rundir,
            stdout=fp,
            stderr=asyncio.subprocess.STDOUT)
        
        status = await proc.wait()
        
        fp.close()

        return TaskDataResult(
            status=status
        )


