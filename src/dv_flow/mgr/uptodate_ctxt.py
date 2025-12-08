#****************************************************************************
#* uptodate_ctxt.py
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
import dataclasses as dc
import os
from typing import Any, Dict, List, Optional

@dc.dataclass
class UpToDateCtxt:
    """Context passed to custom up-to-date check methods"""
    rundir: str
    srcdir: str
    params: Any
    inputs: List[Any]
    exec_data: dict  # Previous exec.json contents
    memento: Optional[Any] = None  # Previous memento from task result

    async def exec(self, 
                   cmd: List[str],
                   cwd: str = None,
                   env: Dict[str, str] = None) -> int:
        """
        Run a subprocess for dependency checking.
        Returns the exit status code.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=(cwd if cwd is not None else self.rundir),
            env=env)
        
        return await proc.wait()
