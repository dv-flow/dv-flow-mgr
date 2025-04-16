#****************************************************************************
#* fileset.py
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
import fnmatch
import glob
import logging
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import ClassVar, List, Tuple
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr import FileSet as _FileSet

class TaskFileSetMemento(BaseModel):
    files : List[Tuple[str,float]] = dc.Field(default_factory=list)

_log = logging.getLogger("FileSet")

async def FileSet(runner, input) -> TaskDataResult:
    _log.debug("TaskFileSet run: %s: basedir=%s, base=%s type=%s include=%s" % (
        input.name,
        input.srcdir,
        input.params.base, input.params.type, str(input.params.include)
    ))


    changed = False
    # 
    try:
        ex_memento = TaskFileSetMemento(**input.memento) if input.memento is not None else None
    except Exception as e:
        _log.error("Failed to load memento: %s" % str(e))
        ex_memento = None 
    memento = TaskFileSetMemento()

    _log.debug("ex_memento: %s" % str(ex_memento))
    _log.debug("params: %s" % str(input.params))

    if input.params is not None:
        glob_root = os.path.join(input.srcdir, input.params.base)
        glob_root = glob_root.strip()

        if glob_root[-1] == '/' or glob_root == '\\':
            glob_root = glob_root[:-1]

        _log.debug("glob_root: %s" % glob_root)

        # TODO: throw error if 'type' is not set

        fs = _FileSet(
                filetype=input.params.type,
                src=input.name, 
                basedir=glob_root)

        if not isinstance(input.params.include, list):
            input.params.include = [input.params.include]

        included_files = []
        for pattern in input.params.include:
            included_files.extend(glob.glob(os.path.join(glob_root, pattern), recursive=False))

        _log.debug("included_files: %s" % str(included_files))

        for file in included_files:
            if not any(glob.fnmatch.fnmatch(file, os.path.join(glob_root, pattern)) for pattern in input.params.exclude):
                memento.files.append((file, os.path.getmtime(os.path.join(glob_root, file))))
                fs.files.append(file[len(glob_root)+1:])

        if input.params.incdirs is not None:
            if isinstance(input.params.incdirs, list):
                fs.incdirs.extend(input.params.incdirs)
            else:
                incdirs = input.params.incdirs.split()
                fs.incdirs.extend(incdirs)
        if input.params.defines is not None:
            if isinstance(input.params.defines, list):
                fs.defines.extend(input.params.defines)
            else:
                defines = input.params.defines.split()
                fs.defines.extend(defines)

    # Check to see if the filelist or fileset have changed
    # Only bother doing this if the upstream task data has not changed
    if ex_memento is not None and not input.changed:
        ex_memento.files.sort(key=lambda x: x[0])
        memento.files.sort(key=lambda x: x[0])
        _log.debug("ex_memento.files: %s" % str(ex_memento.files))
        _log.debug("memento.files: %s" % str(memento.files))
        changed = ex_memento != memento
    else:
        changed = True

    _log.debug("<-- FileSet(%s) changed=%s" % (input.name, changed))

    return TaskDataResult(
        memento=memento,
        changed=changed,
        output=[fs]
    )
