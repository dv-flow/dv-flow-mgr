#****************************************************************************
#* create_file.py
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
import os
import hashlib
import logging
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import ClassVar, List, Tuple
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr import FileSet as _FileSet

class TaskCreateFileMemento(BaseModel):
    name : str = ""
    hash : str = ""

_log = logging.getLogger("CreateFile")

async def CreateFile(runner, input) -> TaskDataResult:
    _log.debug("CreateFile run: %s: rundir=%s, type=%s filename=%s content=%s" % (
        input.name,
        input.rundir,
        input.params.type, input.params.filename, input.params.content))

    # 
    try:
        ex_memento = TaskCreateFileMemento(**input.memento) if input.memento is not None else None
    except Exception as e:
        _log.error("Failed to load memento: %s" % str(e))
        ex_memento = None 
    memento = TaskCreateFileMemento()

    _log.debug("ex_memento: %s" % str(ex_memento))
    _log.debug("params: %s" % str(input.params))

    changed = (input.changed or ex_memento is None)

    if not changed and ex_memento is not None:
        if ex_memento.name != input.params.filename:
            changed = True
        else:
            new_hash = hashlib.md5(input.params.content.encode()).hexdigest()
            changed = ex_memento.hash != new_hash
    
    if changed:
        filename = os.path.join(input.rundir, input.params.filename)
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "w") as fp:
            fp.write(input.params.content)
        memento.name = input.params.filename
        memento.hash = hashlib.md5(input.params.content.encode()).hexdigest()
    else:
        memento = ex_memento

    fs = _FileSet(
                filetype=input.params.type,
                src=input.name, 
                basedir=input.rundir,
                files=[input.params.filename])
    
    if input.params.incdir:
        fs.incdirs = [input.rundir]

    _log.debug("<-- FileSet(%s) changed=%s" % (input.name, changed))

    return TaskDataResult(
        memento=memento,
        changed=changed,
        output=[fs]
    )
