#****************************************************************************
#* publish.py -- std.PubSet + std.Publish
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
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
#****************************************************************************
"""Publish declared FileSet deliverables into a per-run output-data directory.

A run's output-data directory is ``<root_rundir>/out/<run-id>`` and
``out/latest`` symlinks to the newest one. ``std.Publish`` copies the files of
its consumed ``std.FileSet`` / ``std.PubSet`` inputs into that directory,
recording provenance in ``.dfm-publish.json`` and detecting when two sources
write conflicting content to the same destination path.

Path mapping (``dst_rel = task.dest / policy.dest / rebase(f, policy.strip)``):
  * ``dest``    -- additive base sub-path (task ``dest`` composes in front of a
                   PubSet's own ``dest``)
  * ``strip``   -- signed rebase of the file's basedir-relative path ``f``:
                   ``>0`` drop N leading components; ``0`` keep; ``<0`` graft the
                   last ``|N|`` components of ``basedir`` on front
  * ``flatten`` -- publish basename only (overrides ``strip``)

A ``std.PubSet`` is a ``std.FileSet`` subtype that carries a placement policy, so
``Publish`` handles bare FileSets and PubSets uniformly: a PubSet is "a FileSet
that brought its own placement rule".
"""
import fnmatch
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Tuple

import pydantic.dataclasses as dc
from pydantic import BaseModel

from dv_flow.mgr import TaskDataResult
from dv_flow.mgr import FileSet as _FileSet
from dv_flow.mgr.task_data import TaskMarker, SeverityE
from dv_flow.mgr.cache_lock import FileLock

_log = logging.getLogger("Publish")

MANIFEST_SCHEMA = "dvflow-publish/1"
MANIFEST_NAME = ".dfm-publish.json"
LOCK_NAME = ".dfm-publish.lock"

_SEV = {
    "error": SeverityE.Error,
    "warning": SeverityE.Warning,
    "info": SeverityE.Info,
}


class PubSet(_FileSet):
    """A FileSet carrying a placement policy for std.Publish."""
    type : str = "std.PubSet"
    dest : str = ""
    strip : int = 0
    flatten : bool = False


class TaskPublishMemento(BaseModel):
    run_id : str = ""
    entries : List[Tuple[str, str]] = dc.Field(default_factory=list)  # (dst_rel, sha256)


#*** Path algebra ***********************************************************

class _Policy(object):
    __slots__ = ("dest", "strip", "flatten")

    def __init__(self, dest, strip, flatten):
        self.dest = dest or ""
        self.strip = int(strip or 0)
        self.flatten = bool(flatten)


def _join(a, b):
    """os.path.join that treats an empty component as identity."""
    a = a or ""
    b = b or ""
    if a and b:
        return os.path.join(a, b)
    return a or b


def _place(pol, f, basedir):
    """Map a basedir-relative source path 'f' to a destination-relative path."""
    parts = [p for p in f.split(os.sep) if p != ""]
    if pol.flatten:
        rel = parts[-1] if parts else f
    elif pol.strip > 0:
        rel = os.sep.join(parts[pol.strip:]) or (parts[-1] if parts else f)
    elif pol.strip < 0:
        graft = [p for p in (basedir or "").split(os.sep) if p != ""]
        rel = os.sep.join(graft[pol.strip:] + parts)
    else:
        rel = f
    return _join(pol.dest, rel)


def _select(fs, include):
    files = list(getattr(fs, "files", []) or [])
    if not include:
        return files
    inc = include if isinstance(include, list) else [include]
    inc = [p for p in inc if p]
    if not inc:
        return files
    return [f for f in files if any(fnmatch.fnmatch(f, pat) for pat in inc)]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_symlink(target, link_path):
    """Point link_path at target atomically (relative target, os.replace)."""
    d = os.path.dirname(link_path)
    tmp = os.path.join(d, ".%s.tmp" % os.path.basename(link_path))
    try:
        if os.path.islink(tmp) or os.path.exists(tmp):
            os.remove(tmp)
    except OSError:
        pass
    os.symlink(target, tmp)
    os.replace(tmp, link_path)


def _manifest_path(out_dir):
    return os.path.join(out_dir, MANIFEST_NAME)


def _load_manifest(out_dir, run_id):
    p = _manifest_path(out_dir)
    if os.path.isfile(p):
        try:
            with open(p) as fp:
                m = json.load(fp)
            if "entries" not in m:
                m["entries"] = {}
            return m
        except Exception as e:
            _log.warning("Failed to load publish manifest %s: %s" % (p, e))
    return {"schema": MANIFEST_SCHEMA, "run_id": run_id, "entries": {}}


def _save_manifest(out_dir, manifest):
    with open(_manifest_path(out_dir), "w") as fp:
        json.dump(manifest, fp, indent=2, sort_keys=True)


import contextlib


@contextlib.contextmanager
def _sync_lock(lock_path):
    """Synchronous exclusive flock, for the (non-async) CLI publish path."""
    import fcntl
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def publish_files(out_dir, entries, groups, include, on_conflict, publish_task):
    """Copy each (fileset, policy) group's files into out_dir, updating the
    provenance `entries` dict in place (caller holds the lock and saves it).

    A group's fileset supplies ``basedir``/``files``/``filetype``/``src``.
    Returns ``(published_rel_paths, markers, status)`` where ``markers`` is a
    list of ``(severity_str, msg)`` and ``status`` is 0 (ok) or 1 (conflict/error).
    """
    published = []
    markers = []
    status = 0
    for fs, pol in groups:
        for f in _select(fs, include):
            src = os.path.join(fs.basedir, f)
            if not os.path.isfile(src):
                markers.append(("error", "publish: source file not found: %s" % src))
                status = 1
                continue

            dst_rel = _place(pol, f, fs.basedir)
            sha = _sha256(src)
            prev = entries.get(dst_rel)

            do_copy = True
            record = True
            if prev is not None:
                if prev.get("sha256") == sha:
                    do_copy = False               # identical content already there
                else:
                    msg = ("publish conflict at '%s': %s [%s] vs %s [%s]" % (
                        dst_rel, prev.get("src_task"), (prev.get("sha256") or "")[:8],
                        fs.src, sha[:8]))
                    if on_conflict == "error":
                        markers.append(("error", msg))
                        status = 1
                        do_copy = record = False
                    elif on_conflict == "warn":
                        markers.append(("warning", msg))
                        do_copy = record = False
                    elif on_conflict == "skip":
                        markers.append(("info", msg))
                        do_copy = record = False
                    elif on_conflict == "replace":
                        markers.append(("warning", "publish replaced '%s' (%s -> %s)" % (
                            dst_rel, prev.get("src_task"), fs.src)))
                        do_copy = record = True

            if do_copy:
                dst = os.path.join(out_dir, dst_rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

            if record:
                entries[dst_rel] = {
                    "publish_task": publish_task,
                    "src_task": fs.src,
                    "src_path": f,
                    "src_basedir": fs.basedir,
                    "filetype": getattr(fs, "filetype", ""),
                    "sha256": sha,
                    "bytes": os.path.getsize(src),
                }
                if dst_rel not in published:
                    published.append(dst_rel)

    return published, markers, status


def run_publish_cli(out_dir, run_id, files, basedir, dest, strip, flatten,
                    include, on_conflict, filetype, src, publish_task):
    """Non-async publish used by the ``dfm-out publish`` shell verb. Copies the
    given files into out_dir under one policy, maintaining the manifest and the
    ``out/latest`` symlink. Returns ``(status, published_rel_paths, markers)``.
    """
    os.makedirs(out_dir, exist_ok=True)
    _atomic_symlink(run_id, os.path.join(os.path.dirname(out_dir), "latest"))

    fs = _FileSet(filetype=filetype or "", basedir=basedir, src=src or "",
                  files=list(files))
    pol = _Policy(dest, strip, flatten)

    with _sync_lock(os.path.join(out_dir, LOCK_NAME)):
        manifest = _load_manifest(out_dir, run_id)
        published, markers, status = publish_files(
            out_dir, manifest["entries"], [(fs, pol)], include, on_conflict,
            publish_task)
        _save_manifest(out_dir, manifest)

    return status, published, markers


#*** std.PubSet *************************************************************

async def PubSetTask(ctxt, input) -> TaskDataResult:
    """Consume FileSets and emit PubSets stamped with a placement policy."""
    dest = input.params.dest
    strip = input.params.strip
    flatten = input.params.flatten

    output = []
    for item in input.inputs:
        if getattr(item, "type", None) == "std.FileSet":
            output.append(PubSet(
                filetype=getattr(item, "filetype", ""),
                basedir=item.basedir,
                files=list(getattr(item, "files", []) or []),
                incdirs=list(getattr(item, "incdirs", []) or []),
                defines=list(getattr(item, "defines", []) or []),
                attributes=list(getattr(item, "attributes", []) or []),
                dest=dest,
                strip=strip,
                flatten=flatten))

    return TaskDataResult(output=output, changed=input.changed)


#*** std.Publish ***********************************************************

async def Publish(ctxt, input) -> TaskDataResult:
    out_dir = ctxt.out_dir
    os.makedirs(out_dir, exist_ok=True)
    _atomic_symlink(ctxt.run_id, os.path.join(ctxt.root_rundir, "out", "latest"))

    base = input.params.dest
    default_pol = _Policy(base, input.params.strip, input.params.flatten)
    include = input.params.include or []
    on_conflict = input.params.on_conflict or "error"

    # Normalize inputs to (fileset, policy) groups. task.dest composes as a base
    # prefix in front of a PubSet's own dest (and is the default for bare inputs).
    groups = []
    for item in input.inputs:
        itype = getattr(item, "type", None)
        if itype == "std.PubSet":
            groups.append((item, _Policy(
                _join(base, getattr(item, "dest", "")),
                getattr(item, "strip", 0),
                getattr(item, "flatten", False))))
        elif itype == "std.FileSet":
            groups.append((item, default_pol))

    async with FileLock(Path(os.path.join(out_dir, LOCK_NAME))):
        manifest = _load_manifest(out_dir, ctxt.run_id)
        published_files, raw_markers, status = publish_files(
            out_dir, manifest["entries"], groups, include, on_conflict, input.name)
        _save_manifest(out_dir, manifest)

    markers = [TaskMarker(msg=msg, severity=_SEV[sev]) for sev, msg in raw_markers]
    published = _FileSet(filetype="", src=input.name, basedir=out_dir,
                         files=published_files)
    memento = TaskPublishMemento(
        run_id=ctxt.run_id,
        entries=[(rel, manifest["entries"][rel]["sha256"]) for rel in published_files])

    return TaskDataResult(
        output=[published],
        status=status,
        markers=markers,
        memento=memento.model_dump(),
        changed=True)
