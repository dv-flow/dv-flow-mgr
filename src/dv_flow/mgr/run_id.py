#****************************************************************************
#* run_id.py -- per-run output-data identity
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
"""A run's output-data directory lives at ``<rundir>/out/<run-id>``. Every
``dfm run`` writes its run record (``results.json``) there, and every
``std.Publish`` task in the run publishes into the same directory.

The id is a local timestamp, ``YYYYMMDD-HHMMSS``, with a ``-2``, ``-3`` ...
suffix when two runs land in the same second. ``dfm run`` allocates it eagerly:
``alloc_run_id`` creates ``out/<run-id>`` with ``os.mkdir``, so two runs that
start in the same rundir in the same second still get distinct ids.
``out/latest`` links to the newest run (``set_latest``).

Ids written by older versions are zero-padded counters (``0001``);
``is_run_id`` accepts both forms.
"""
import os
import re
import time

_TS_RE = re.compile(r"[0-9]{8}-[0-9]{6}(-[0-9]+)?")
_LEGACY_RE = re.compile(r"[0-9]{4,}")


def is_run_id(name: str) -> bool:
    """True if ``name`` is an allocated run-id: the timestamp form
    (``20261031-142210``, ``20261031-142210-2``) or the legacy counter form
    (``0003``). Explicit ids (``--run-id ci-42``) are not recognized."""
    return bool(_TS_RE.fullmatch(name) or _LEGACY_RE.fullmatch(name))


def alloc_run_id(root_rundir: str, now=None, create: bool = True) -> str:
    """Allocate this run's id under ``<root_rundir>/out``.

    ``now`` is a ``time.time()``-style float (default: the current time).
    With ``create`` (the default) the directory ``out/<run-id>`` is made with
    ``os.mkdir`` in a retry loop, which makes allocation atomic across
    concurrent runs. ``create=False`` only picks an id that does not exist yet;
    the first writer creates the directory (programmatic graph builds use this,
    so that building a graph without running it leaves no trace).
    """
    if now is None:
        now = time.time()
    base = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    out = os.path.join(root_rundir, "out")
    if create:
        os.makedirs(out, exist_ok=True)

    n = 1
    while True:
        rid = base if n == 1 else "%s-%d" % (base, n)
        path = os.path.join(out, rid)
        if create:
            try:
                os.mkdir(path)
                return rid
            except FileExistsError:
                pass
        elif not os.path.lexists(path):
            return rid
        n += 1


def set_latest(out_root: str, run_id: str) -> None:
    """Point ``<out_root>/latest`` at ``run_id`` atomically (a relative link,
    replaced with ``os.replace``). ``out_root`` is the ``out/`` directory."""
    os.makedirs(out_root, exist_ok=True)
    link_path = os.path.join(out_root, "latest")
    tmp = os.path.join(out_root, ".latest.%d.tmp" % os.getpid())
    try:
        if os.path.lexists(tmp):
            os.remove(tmp)
    except OSError:
        pass
    os.symlink(run_id, tmp)
    os.replace(tmp, link_path)
