#****************************************************************************
#* retention.py -- pruning old run records, and copying logs
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
"""Retention (``results.keep_previous``) and ``results.copy_logs``.

Pruning keeps the current run and the ``keep_previous`` newest earlier ones
under ``rundir/out`` (newest by the record's mtime) and removes the rest.
Only allocated run-ids are candidates (``is_run_id``: timestamps and legacy
counters); an explicit ``--run-id`` directory, ``latest``'s target and the
current run are never removed and do not count. A pruned run's
``std.Publish`` outputs go with it, since they share ``out/<run-id>``.
``keep_previous: None`` (``all`` in the config) never prunes.
"""
import logging
import os
import shutil
from typing import Dict, List, Optional

from ..run_id import is_run_id
from .recorder import RESULTS_FILE

_log = logging.getLogger("results.retention")


def _mtime(d: str) -> float:
    p = os.path.join(d, RESULTS_FILE)
    try:
        return os.path.getmtime(p if os.path.isfile(p) else d)
    except OSError:
        return 0.0


def prune(out_root: str, keep_previous: Optional[int], current: str = None) -> List[str]:
    """Remove the run dirs older than the ``keep_previous`` newest besides
    ``current``; returns the ids removed. None never prunes."""
    if keep_previous is None or keep_previous < 0 or not os.path.isdir(out_root):
        return []
    protect = {current} if current else set()
    latest = os.path.join(out_root, "latest")
    if os.path.islink(latest):
        protect.add(os.path.basename(os.path.realpath(latest)))
    cands = []
    for name in os.listdir(out_root):
        d = os.path.join(out_root, name)
        if name == "latest" or os.path.islink(d) or not os.path.isdir(d):
            continue
        if not is_run_id(name) or name in protect:
            continue
        cands.append((_mtime(d), name))
    cands.sort(reverse=True)
    removed = []
    for i, (_, name) in enumerate(cands):
        if i < keep_previous:
            continue
        try:
            shutil.rmtree(os.path.join(out_root, name))
            removed.append(name)
        except OSError as e:
            _log.warning("could not remove old run %s: %s" % (name, e))
    return removed


def copy_logs(rf, out_dir: str, rundir: str) -> Dict[str, str]:
    """Copy every ``role=log`` artifact into ``out_dir/logs/`` (keeping its
    path relative to ``rundir``); returns ``{original: copy}``."""
    copies = {}
    logs = os.path.join(out_dir, "logs")
    rundir = os.path.abspath(rundir)

    def visit(n):
        for a in n.artifacts:
            if a.role != "log":
                continue
            for f in a.files:
                p = os.path.abspath(f if os.path.isabs(f) else os.path.join(a.basedir, f))
                if p in copies or not os.path.isfile(p):
                    continue
                rel = os.path.relpath(p, rundir)
                if rel.startswith(".."):
                    rel = os.path.join("_external", os.path.basename(p))
                dst = os.path.join(logs, rel)
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(p, dst)
                    copies[p] = dst
                except OSError as e:
                    _log.warning("could not copy log %s: %s" % (p, e))
        for c in n.children:
            visit(c)
    visit(rf.result)
    return copies
