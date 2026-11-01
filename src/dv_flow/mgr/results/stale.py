#****************************************************************************
#* stale.py -- artifact staleness against the recorded stamps
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
"""Compare each artifact's recorded ``mtime``/``size`` with the file now.
Task rundirs are reused across runs, so an old record's waves may have been
overwritten since. Readers annotate (``state``: ok | stale | missing, and
``stale`` on the artifact); ``results.json`` itself is never rewritten."""
import os


def stamp_state(st) -> str:
    try:
        s = os.stat(st["path"])
    except OSError:
        return "missing"
    if st.get("mtime") is None and st.get("size") is None:
        return "missing"    # recorded as absent
    if (st.get("size") is not None and s.st_size != st["size"]) or \
       (st.get("mtime") is not None and abs(s.st_mtime - st["mtime"]) > 1e-3):
        return "stale"
    return "ok"


def annotate(doc) -> dict:
    """Annotate a results.json dict in place; returns it."""
    def visit(n):
        for a in n.get("artifacts") or []:
            bad = False
            for st in a.get("stamps") or []:
                st["state"] = stamp_state(st)
                bad = bad or st["state"] != "ok"
            if a.get("stamps"):
                a["stale"] = bad
        for c in n.get("children") or []:
            visit(c)
    if isinstance(doc.get("result"), dict):
        visit(doc["result"])
    return doc
