#****************************************************************************
#* rootcheck.py -- the root-task rule: a root produces a std.Result
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
"""The root-task rule: a ``scope: root`` task -- what a user runs -- declares
a ``std.Result`` (an is-a match) in its ``produces:``.

Rolled out in phases. Today a root without one gets a warning in ``dfm
validate`` and at graph build, and dfm synthesizes a ``std.TaskResult`` for
it at run time; ``results.strict_roots: true`` makes it an error.
"""
from typing import Any, Callable, List, Optional

from ..type_match import is_a, normalize

RESULT_TYPE = "std.Result"
HINT = ("declare what it reports, e.g.\n"
        "  produces:\n"
        "  - type: std.Result      # or any subtype of it\n"
        "(dfm makes a std.TaskResult for it meanwhile)")


def produced_types(produces) -> List[str]:
    out = []
    for entry in produces or []:
        p = normalize(entry)
        if p and p.get("type"):
            out.append(str(p["type"]))
    return out


def declared_produces(task, node_produces=None):
    """What a task declares it produces: the nearest non-empty `produces:`
    along its `uses:` chain (an override alias can carry an empty list),
    else the built node's."""
    t = task
    seen = set()
    while t is not None and id(t) not in seen:
        seen.add(id(t))
        p = getattr(t, "produces", None)
        if p:
            return p
        t = getattr(t, "uses", None)
    return node_produces


def produces_result(produces, resolve: Optional[Callable] = None,
                    want: str = RESULT_TYPE) -> bool:
    return any(is_a(t, want, resolve) for t in produced_types(produces))


def root_problem(task, produces=None, resolve: Optional[Callable] = None) -> Optional[str]:
    """The diagnostic for a root task that declares no Result, or None. The
    task's own (inherited) declaration wins; ``produces`` (a built node's) is
    the fallback when the task declares nothing."""
    if not getattr(task, "is_root", False):
        return None
    produces = declared_produces(task, produces)
    if produces_result(produces, resolve):
        return None
    name = getattr(task, "name", "?")
    have = produced_types(produces)
    return ("root task '%s' declares no std.Result in produces:%s" % (
        name, (" (it declares %s)" % ", ".join(have)) if have else ""))


_PORT_KEEP = ("std.Env", "std.TaskFailure")


def filter_root_port(node, resolve: Optional[Callable] = None) -> bool:
    """Phase B of the rule: a root task that declares a std.Result hands its
    dependants only Result items (plus `std.Env` and `std.TaskFailure`, which
    are plumbing, not outputs). They reach files through the Results'
    artifacts (`results.api.artifacts`). A root that declares no Result is
    left alone -- it is warned about instead, and filtering it would starve
    a dependant that has no Result to read. Returns True if it filtered."""
    from ..task_data import TaskDataOutput
    from .collect import is_result
    td = getattr(node, "taskdef", None)
    if td is None or not getattr(td, "is_root", False):
        return False
    if not produces_result(declared_produces(td, getattr(node, "produces", None)), resolve):
        return False
    out = getattr(node, "output", None)
    items = getattr(out, "output", None)
    if not items:
        return False
    kept = [it for it in items
            if getattr(it, "type", None) in _PORT_KEEP or is_result(it, resolve)]
    if len(kept) == len(items):
        return False
    node.output = TaskDataOutput(changed=out.changed, dep_m=dict(out.dep_m or {}),
                                 output=kept)
    return True
