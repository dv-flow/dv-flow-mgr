#****************************************************************************
#* exec.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*  
#*   http://www.apache.org/licenses/LICENSE-2.0
#*  
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
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

