import asyncio
import dataclasses as dc
from pydantic import BaseModel
import pydantic.dataclasses as pdc
import os
from typing import List
from .task_data import TaskMarker, SeverityE, TaskMarkerLoc

class ExecInfo(BaseModel):
    cmd : List[str] = pdc.Field(default_factory=list)
    status : int = pdc.Field(default=0)

@dc.dataclass
class TaskRunCtxt(object):
    runner : 'TaskRunner'
    rundir : str
    _markers : List[TaskMarker] = dc.field(default_factory=list)
    _exec_info : List[ExecInfo] = dc.field(default_factory=list)

    async def exec(self, 
                   cmd : List[str],
                   logfile=None,
                   logfilter=None,
                   cwd=None,
                   env=None):
        """
        Executes a command as part of the task's implementation.
        Output from the command will be saved to the specified logfile,
        or to a default logfile if not specified. If the command
        fails, an error marker will be added.

        Example:
        
        .. code-block:: python

            status |= await runner.exec(['ls', '-l'], logfile='ls.log')

        """
        if logfile is None:
            logfile = "cmd_%d.log" % (self._exec_info.__len__() + 1)

        fp = open(os.path.join(self.rundir, logfile), "w")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=fp,
            stderr=asyncio.subprocess.STDOUT,
            cwd=(cwd if cwd is not None else self.rundir),
            env=env)
        fp.close()
        
        status = await proc.wait()

        self._exec_info.append(ExecInfo(cmd=cmd, status=status))

        if status != 0:
            self.error("Command failed: %s" % " ".join(cmd))

        return status

    def create(self, path, content):
        """Create a file in the task's rundir"""
        if not os.path.isabs(path):
            path = os.path.join(self.rundir, path)
        
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        with open(path, "w") as fp:
            fp.write(content)


    def marker(self, msg : str, severity : SeverityE, loc : TaskMarkerLoc=None):
        """Add a marker related to the task's execution"""
        if loc is not None:
            self._markers.append(TaskMarker(msg=msg, severity=severity, loc=loc))
        else:
            self._markers.append(TaskMarker(msg=msg, severity=severity))

    def error(self, msg : str, loc : TaskMarkerLoc=None):
        """Add an error marker related to the task's execution"""
        self.marker(msg=msg, severity=SeverityE.Error, loc=loc)
