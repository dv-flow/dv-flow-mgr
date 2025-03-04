
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
    ex_memento = input.memento
    memento = TaskFileSetMemento()

    _log.debug("ex_memento: %s" % str(ex_memento))
    _log.debug("params: %s" % str(input.params))

    if input.params is not None:
        glob_root = os.path.join(input.srcdir, input.params.base)
        glob_root = glob_root.strip()

        if glob_root[-1] == '/' or glob_root == '\\':
            glob_root = glob_root[:-1]

        _log.debug("glob_root: %s" % glob_root)

        fs = _FileSet(
                src=input.name, 
                type=input.params.type,
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

    return TaskDataResult(
        memento=memento,
        changed=changed,
        output=[fs]
    )
