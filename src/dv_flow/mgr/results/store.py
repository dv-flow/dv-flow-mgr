#****************************************************************************
#* store.py -- finding and loading run records
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
"""Find and load the run records under ``<rundir>/out``."""
import json
import os
from typing import List, Optional, Tuple

from .recorder import RESULTS_FILE


class RecordNotFound(Exception):
    pass


def out_root(rundir: str) -> str:
    return os.path.join(rundir, "out")


def list_records(rundir: str) -> List[Tuple[str, str]]:
    """``[(run_id, path)]`` of every ``out/<id>/results.json``, newest first
    (by the file's mtime, so explicit ids like ``ci-42`` sort correctly)."""
    out = out_root(rundir)
    ret = []
    if not os.path.isdir(out):
        return ret
    for name in os.listdir(out):
        if name == "latest":
            continue
        p = os.path.join(out, name, RESULTS_FILE)
        if os.path.isfile(p):
            ret.append((os.path.getmtime(p), name, p))
    ret.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [(n, p) for _, n, p in ret]


def resolve_run(rundir: str, run: Optional[str] = None) -> Tuple[str, str]:
    """``(run_id, path)`` for ``run`` (an id, or ``latest``/None)."""
    out = out_root(rundir)
    if run in (None, "", "latest"):
        link = os.path.join(out, "latest")
        if os.path.islink(link) or os.path.isdir(link):
            rid = os.path.basename(os.path.realpath(link))
            p = os.path.join(out, rid, RESULTS_FILE)
            if os.path.isfile(p):
                return rid, p
        recs = list_records(rundir)
        if recs:
            return recs[0]
        raise RecordNotFound("no results under %s; run `dfm run <task>` first" % out)
    p = os.path.join(out, run, RESULTS_FILE)
    if not os.path.isfile(p):
        raise RecordNotFound("no results for run '%s' under %s" % (run, out))
    return run, p


def load_record(rundir: str, run: Optional[str] = None) -> dict:
    """The record as a dict (with ``run.id`` set even for an old record)."""
    rid, p = resolve_run(rundir, run)
    with open(p) as fp:
        d = json.load(fp)
    d.setdefault("run", {}).setdefault("id", rid)
    return d


def results_json(rundir: str, run: Optional[str] = None, failures_only: bool = False) -> str:
    """What `dfm show results --json [--failures]` prints: the record with
    artifact staleness marked, or only its `summary`. A missing record is
    `{"error": ...}`."""
    from .stale import annotate
    try:
        doc = annotate(load_record(rundir, run))
    except RecordNotFound as e:
        return json.dumps({"error": str(e)})
    return json.dumps(doc["summary"] if failures_only else doc, indent=2)
