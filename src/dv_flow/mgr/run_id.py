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
``std.Publish`` task in a single run shares one run-id so they all publish into
the same directory. The id is a zero-padded monotonic counter, allocated once
per run by scanning the existing ``out/`` entries and taking ``max+1``.
"""
import os
import re

_RUN_ID_RE = re.compile(r"0*([0-9]+)$")


def alloc_run_id(root_rundir: str) -> str:
    """Allocate the next run-id by scanning ``<root_rundir>/out`` for existing
    numeric entries. Returns a zero-padded string (e.g. ``"0001"``). Does not
    create any directory -- the first publisher creates ``out/<run-id>`` lazily,
    so a run that publishes nothing leaves no trace and does not consume an id.
    """
    out = os.path.join(root_rundir, "out")
    mx = 0
    if os.path.isdir(out):
        for name in os.listdir(out):
            m = _RUN_ID_RE.fullmatch(name)
            if m:
                try:
                    mx = max(mx, int(m.group(1)))
                except ValueError:
                    pass
    return "%04d" % (mx + 1)
