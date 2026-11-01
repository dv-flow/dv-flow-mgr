#****************************************************************************
#* render_md.py -- results.json as markdown (summary.md)
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
"""``summary.md``: the run record as markdown. Pure (no I/O)."""
from .model import ResultsFile
from .status import is_ok

_ICON = {"pass": "✅", "fail": "❌", "error": "💥", "timeout": "⏱",
         "skip": "⏭", "notrun": "⛔"}


def _fmt_metric(name, m):
    v = m.value
    vs = ("%d" % v) if float(v).is_integer() else ("%.4g" % v)
    return "%s %s%s" % (name, vs, (" " + m.unit) if m.unit else "")


def render_md(rf: ResultsFile) -> str:
    s = rf.summary
    lines = ["# %s %s: %s" % (_ICON.get(s.status, ""), rf.run.root if isinstance(rf.run.root, str)
                              else ", ".join(rf.run.root), s.status), ""]
    if s.msg:
        lines += [s.msg, ""]
    c = s.counts
    if c.get("total"):
        cols = [k for k in ("total", "pass", "fail", "error", "timeout", "notrun", "skip")
                if k == "total" or c.get(k)]
        lines += ["| " + " | ".join(cols) + " |",
                  "|" + "---|" * len(cols),
                  "| " + " | ".join(str(c.get(k, 0)) for k in cols) + " |", ""]
    if s.metrics:
        lines += ["Metrics: " + ", ".join(_fmt_metric(k, m) for k, m in s.metrics.items()), ""]
    if s.failures:
        lines += ["## Failures", ""]
        for f in s.failures:
            lines.append("- %s **%s** `%s`%s" % (_ICON.get(f.status, ""), f.status, f.path,
                                                 (": " + f.msg) if f.msg else ""))
            for ck in f.checks:
                lines.append("  - check `%s`: %s%s" % (ck.name, ck.status,
                                                        (" (" + ck.msg + ")") if ck.msg else ""))
            if f.log is not None:
                lines.append("  - log: `%s%s`" % (f.log.path, (":%d" % f.log.line) if f.log.line else ""))
            if f.waves:
                lines.append("  - waves: `%s`" % f.waves)
        lines.append("")
    lines.append("Run `%s` · %s" % (rf.run.id, rf.run.end_time or ""))
    return "\n".join(lines) + "\n"
