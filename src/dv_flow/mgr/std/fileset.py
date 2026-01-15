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
from dv_flow.mgr.task_data import TaskMarker, SeverityE

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
    status = 0
    markers = []
    
    try:
        ex_memento = TaskFileSetMemento(**input.memento) if input.memento is not None else None
    except Exception as e:
        _log.error("Failed to load memento: %s" % str(e))
        ex_memento = None 
    memento = TaskFileSetMemento()

    _log.debug("ex_memento: %s" % str(ex_memento))
    _log.debug("params: %s" % str(input.params))

    if input.params is not None:
        base = input.params.base.strip()
        # Check for glob pattern in base
        is_glob = any(c in base for c in ['*', '?', '['])
        if os.path.isabs(base):
            base_candidates = glob.glob(base, recursive=True) if is_glob else [base]
        else:
            base_path = os.path.join(input.srcdir, base)
            base_candidates = glob.glob(base_path, recursive=True) if is_glob else [base_path]
        if is_glob:
            if len(base_candidates) == 0:
                raise RuntimeError(f"No directories match glob pattern: {base}")
            if len(base_candidates) > 1:
                raise RuntimeError(f"Multiple directories match glob pattern: {base_candidates}")
            glob_root = base_candidates[0]
        else:
            glob_root = base_candidates[0]

        if glob_root[-1] == '/' or glob_root == '\\':
            glob_root = glob_root[:-1]

        _log.debug("glob_root: %s" % glob_root)

        # TODO: throw error if 'type' is not set

        fs = _FileSet(
                filetype=input.params.type,
                src=input.name, 
                basedir=glob_root)

        if not isinstance(input.params.include, list):
            input.params.include = [input.params.include] if input.params.include else []
        
        if not isinstance(input.params.exclude, list):
            input.params.exclude = [input.params.exclude] if input.params.exclude else []

        included_files = []
        for pattern in input.params.include:
            if pattern:  # Skip empty patterns
                matched_files = glob.glob(os.path.join(glob_root, pattern), recursive=False)
                if not matched_files:
                    error_msg = "Include pattern '%s' did not match any files in '%s'" % (pattern, glob_root)
                    _log.error(error_msg)
                    markers.append(TaskMarker(
                        msg=error_msg,
                        severity=SeverityE.Error
                    ))
                    status = 1
                included_files.extend(matched_files)

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
        if hasattr(input.params, 'attributes') and input.params.attributes is not None:
            if isinstance(input.params.attributes, list):
                fs.attributes.extend(input.params.attributes)
            else:
                attributes = input.params.attributes.split()
                fs.attributes.extend(attributes)

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

    _log.debug("<-- FileSet(%s) changed=%s status=%d" % (input.name, changed, status))

    return TaskDataResult(
        memento=memento,
        changed=changed,
        output=[fs],
        markers=markers,
        status=status
    )


async def FileSetUpToDate(ctxt) -> bool:
    """
    Up-to-date check for FileSet task.
    
    Efficiently checks whether the glob patterns would result in different files
    by comparing the current glob results with the saved memento.
    """
    _log.debug("--> FileSetUpToDate")
    
    # If no memento, not up-to-date
    if ctxt.memento is None:
        _log.debug("FileSetUpToDate: no memento, not up-to-date")
        return False
    
    try:
        ex_memento = TaskFileSetMemento(**ctxt.memento)
    except Exception as e:
        _log.debug("FileSetUpToDate: failed to load memento: %s" % e)
        return False
    
    # Get parameters
    params = ctxt.params
    if params is None:
        _log.debug("FileSetUpToDate: no params, not up-to-date")
        return False
    
    base = params.base.strip() if params.base else ""
    
    # Check for glob pattern in base
    is_glob = any(c in base for c in ['*', '?', '['])
    if os.path.isabs(base):
        base_candidates = glob.glob(base, recursive=True) if is_glob else [base]
    else:
        base_path = os.path.join(ctxt.srcdir, base)
        base_candidates = glob.glob(base_path, recursive=True) if is_glob else [base_path]
    
    if is_glob:
        if len(base_candidates) == 0 or len(base_candidates) > 1:
            # Different number of base candidates than before
            _log.debug("FileSetUpToDate: base glob changed, not up-to-date")
            return False
        glob_root = base_candidates[0]
    else:
        glob_root = base_candidates[0]
    
    if glob_root and (glob_root[-1] == '/' or glob_root[-1] == '\\'):
        glob_root = glob_root[:-1]
    
    # Normalize include/exclude to lists
    include = params.include if isinstance(params.include, list) else ([params.include] if params.include else [])
    exclude = params.exclude if isinstance(params.exclude, list) else ([params.exclude] if params.exclude else [])
    
    # Evaluate glob patterns to get current files
    included_files = []
    for pattern in include:
        if pattern:
            included_files.extend(glob.glob(os.path.join(glob_root, pattern), recursive=False))
    
    # Build current memento
    current_files = []
    for file in included_files:
        if not any(fnmatch.fnmatch(file, os.path.join(glob_root, pattern)) for pattern in exclude if pattern):
            try:
                mtime = os.path.getmtime(file)
                current_files.append((file, mtime))
            except OSError:
                # File doesn't exist anymore
                _log.debug("FileSetUpToDate: file %s no longer exists" % file)
                return False
    
    # Compare with saved memento
    ex_files = sorted(ex_memento.files, key=lambda x: x[0])
    current_files = sorted(current_files, key=lambda x: x[0])
    
    if len(ex_files) != len(current_files):
        _log.debug("FileSetUpToDate: file count changed (%d -> %d)" % (len(ex_files), len(current_files)))
        return False
    
    for (ex_file, ex_mtime), (cur_file, cur_mtime) in zip(ex_files, current_files):
        if ex_file != cur_file:
            _log.debug("FileSetUpToDate: file list changed")
            return False
        if ex_mtime != cur_mtime:
            _log.debug("FileSetUpToDate: file %s mtime changed" % cur_file)
            return False
    
    _log.debug("<-- FileSetUpToDate: up-to-date")
    return True
