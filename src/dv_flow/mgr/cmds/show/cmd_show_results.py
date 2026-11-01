#****************************************************************************
#* cmd_show_results.py
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
"""Show results sub-command: read a run record (rundir/out/<run-id>/results.json)."""

import json
import logging
import os
import sys
from typing import ClassVar


class CmdShowResults:
    """Print a run's results: the tree, the failures, or the JSON record."""

    _log: ClassVar = logging.getLogger("CmdShowResults")

    def __call__(self, args):
        from ...results import store
        from ...results.model import ResultsFile
        from ...results import render_text as RT

        rundir = getattr(args, "rundir", None) or os.path.join(os.getcwd(), "rundir")
        rundir = os.path.abspath(rundir)

        if getattr(args, "list", False):
            recs = store.list_records(rundir)
            if not recs:
                print("Error: no results under %s; run `dfm run <task>` first"
                      % store.out_root(rundir), file=sys.stderr)
                return 1
            rows = []
            for rid, p in recs:
                try:
                    with open(p) as fp:
                        rows.append((rid, ResultsFile.model_validate(json.load(fp))))
                except Exception:
                    rows.append((rid, None))
            if getattr(args, "json", False):
                print(json.dumps([{"id": rid, "path": p,
                                   "status": rf.summary.status if rf else None,
                                   "root": rf.run.root if rf else None,
                                   "counts": rf.summary.counts if rf else None}
                                  for (rid, p), (_, rf) in zip(recs, rows)], indent=2))
            else:
                sys.stdout.write(RT.render_list(rows))
            return 0

        try:
            doc = store.load_record(rundir, getattr(args, "run", None))
        except store.RecordNotFound as e:
            print("Error: %s" % e, file=sys.stderr)
            return 1

        from ...results.stale import annotate
        annotate(doc)

        fmt = getattr(args, "format", None) or ("json" if getattr(args, "json", False) else "text")
        failures = getattr(args, "failures", False)
        if fmt == "json":
            text = json.dumps(doc["summary"] if failures else doc, indent=2) + "\n"
        else:
            from ...results.render import render
            rf = ResultsFile.model_validate(doc)
            if fmt == "text" and failures:
                text = render(rf, "failures")
            elif fmt == "text":
                text = render(rf, "text", depth=getattr(args, "depth", None),
                              expand=getattr(args, "all", False))
            else:
                text = render(rf, fmt)

        out = getattr(args, "output", None)
        if out:
            with open(out, "w") as fp:
                fp.write(text)
        else:
            sys.stdout.write(text)
        return 0
