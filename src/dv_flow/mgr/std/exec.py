import asyncio
import logging
from dv_flow.mgr import TaskDataResult

_log = logging.getLogger("Exec")

async def Exec(runner, input) -> TaskDataResult:
    _log.debug("TaskExec run: %s: cmd=%s" % (input.name, input.params.command))


    proc = await asyncio.create_subprocess_shell(
        input.params.command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    
    await proc.wait()

    return TaskDataResult()

