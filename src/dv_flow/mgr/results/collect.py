#****************************************************************************
#* collect.py -- finding the Result items among a task's inputs
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
"""Find the ``std.Result`` items among data items, and keep only the top of
each tree: a suite passed through next to its own cases is one result, not
three. Shared by the run recorder and the std aggregators."""
from .convert import as_dict
from .lineage import is_result_type


def runtime_resolver(ctxt):
    """``findType`` for the running task's type registry, or None."""
    r = getattr(ctxt, "runner", None)
    b = getattr(r, "builder", None) or getattr(r, "_builder", None)
    if b is None and r is not None and hasattr(r, "_findType"):
        b = r       # the runner is itself a graph builder
    loader = getattr(b, "loader", None) if b is not None else None
    if loader is not None and hasattr(loader, "findType"):
        return loader.findType
    root = getattr(b, "root_pkg", None) if b is not None else None
    if root is not None and hasattr(b, "_findType"):
        return lambda n: b._findType(root, n)
    return None


_RESULT_FIELDS = ("status", "checks", "children", "metrics")


def is_result(item, resolve=None) -> bool:
    """Is-a ``std.Result`` by the type registry; without one (or for a type
    it doesn't know), by having the Result fields."""
    t = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
    if not t or t == "std.TaskFailure":
        return False
    if resolve is not None:
        try:
            if resolve(t) is not None:
                return is_result_type(t, resolve)
        except Exception:
            pass
    if isinstance(item, dict):
        return all(k in item for k in _RESULT_FIELDS)
    return all(hasattr(item, k) for k in _RESULT_FIELDS)


def _key(d):
    if d.get("src"):
        return (d.get("src"), d.get("seq"), d.get("type"))
    return None


def _trial_keys(item):
    """Keys of the trials a reduced case (std.EvalCase) anywhere in
    ``item``'s tree references -- by producing task and type."""
    keys = set()
    stack = [item]
    while stack:
        n = stack.pop()
        g = n.get if isinstance(n, dict) else (lambda k, _n=n: getattr(_n, k, None))
        for t in g("trials") or []:
            if isinstance(t, dict) and t.get("task"):
                keys.add(("trial", t["task"], t.get("type")))
        stack.extend(g("children") or [])
    return keys


def top_results(items, resolve=None):
    """The Result items in ``items`` that no other item holds as a child
    (``children``, or the older ``results``) or references from ``trials``."""
    res = [it for it in items or [] if is_result(it, resolve)]
    held_ids, held_keys = set(), set()
    for it in res:
        kids = (it.get("children") if isinstance(it, dict) else getattr(it, "children", None)) \
            or (it.get("results") if isinstance(it, dict) else getattr(it, "results", None)) or []
        held_keys.update(_trial_keys(it))
        for c in kids:
            held_ids.add(id(c))
            k = _key(as_dict(c))
            if k is not None:
                held_keys.add(k)
    ret = []
    for it in res:
        if id(it) in held_ids:
            continue
        d = as_dict(it)
        k = _key(d)
        if k is not None and k in held_keys:
            continue
        if ("trial", d.get("task"), d.get("type")) in held_keys:
            continue
        ret.append(it)
    return ret
