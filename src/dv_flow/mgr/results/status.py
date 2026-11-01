#****************************************************************************
#* status.py -- the Result status vocabulary
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
"""The status vocabulary shared by every Result node, check and summary.

``pass``    the work ran and every check passed
``fail``    the work ran and a check failed (a verdict)
``error``   no clean verdict: a crash, a tool error, a flow failure
``timeout`` the work did not finish in time
``skip``    deliberately not run
``notrun``  selected, but not run because something it depends on failed
"""

STATUSES = ("pass", "fail", "error", "timeout", "skip", "notrun")

# Worst first. worst() of two statuses is the one earlier in this list.
_ORDER = ("error", "timeout", "fail", "notrun", "skip", "pass")
_RANK = {s: i for i, s in enumerate(_ORDER)}

CHECK_STATUSES = ("pass", "fail", "error", "skip")


def is_status(status) -> bool:
    return status in _RANK


def is_ok(status) -> bool:
    """True for a status that does not need attention (pass, skip)."""
    return status in ("pass", "skip")


def worst(a, b):
    """The worse of two statuses (error > timeout > fail > notrun > skip > pass).
    ``None`` is the identity."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _RANK.get(a, 0) <= _RANK.get(b, 0) else b


def worst_of(statuses, default=None):
    ret = None
    for s in statuses:
        ret = worst(ret, s)
    return default if ret is None else ret
