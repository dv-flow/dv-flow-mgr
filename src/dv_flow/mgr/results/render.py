#****************************************************************************
#* render.py -- dispatch to the results renderers
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
"""``render(rf, fmt)`` for every rendering of a run record."""
from .model import ResultsFile

RENDERERS = ("text", "failures", "json", "junit", "ctrf", "md")


def render(rf: ResultsFile, fmt: str, **kw) -> str:
    if fmt == "junit":
        from .render_junit import render_junit
        return render_junit(rf)
    if fmt == "ctrf":
        from .render_junit import render_ctrf
        return render_ctrf(rf)
    if fmt == "md":
        from .render_md import render_md
        return render_md(rf)
    if fmt == "text":
        from .render_text import render_tree
        return render_tree(rf, **kw)
    if fmt == "failures":
        from .render_text import render_failures
        return render_failures(rf)
    if fmt == "json":
        import json
        return json.dumps(rf.dump(), indent=2) + "\n"
    raise ValueError("unknown format '%s'" % fmt)
