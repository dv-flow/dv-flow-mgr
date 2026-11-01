#****************************************************************************
#* rollup.py -- roll a Result node up from its children
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
"""Roll-up of a Result node from its children (status, leaf counts, metrics)."""
from .status import STATUSES


def _get(obj, key, dflt=None):
    if isinstance(obj, dict):
        return obj.get(key, dflt)
    return getattr(obj, key, dflt)


# The group node dfm adds under a root for failed tasks no Result accounts
# for (build failures). A node whose only children are such groups is still a
# leaf in its own right.
TASKS_GROUP = "_tasks"


def _children(n):
    return _get(n, "children") or []


def is_leaf(n) -> bool:
    return all(_get(c, "name") == TASKS_GROUP for c in _children(n))


def iter_leaves(nodes):
    """Leaf nodes under ``nodes``, depth first."""
    for n in nodes:
        kids = _children(n)
        if is_leaf(n):
            yield n
            yield from iter_leaves([g for g in kids])
        else:
            yield from iter_leaves(kids)


def leaf_counts(children):
    """``{total, pass, fail, error, timeout, skip, notrun}`` over the leaves."""
    counts = {"total": 0}
    for s in STATUSES:
        counts[s] = 0
    for leaf in iter_leaves(children):
        # A root raised to error by the `_tasks` it gained counts as itself.
        st = _get(leaf, "own_status") or _get(leaf, "status") or "pass"
        counts["total"] += 1
        counts[st] = counts.get(st, 0) + 1
    return counts


# -- metrics ----------------------------------------------------------------

RULES = ("sum", "max", "min", "mean", "none")
_BY_BETTER = {"lower": "sum", "higher": "min", "none": "none"}


def _metric_parts(m):
    """(value, unit, better, label) of a Metric map / model / bare number."""
    if isinstance(m, bool):
        return None, None, None, None
    if isinstance(m, (int, float)):
        return float(m), None, None, None
    v = _get(m, "value")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None, None, None, None
    return float(v), _get(m, "unit"), _get(m, "better"), _get(m, "label")


def metric_rule(name, better=None) -> str:
    """How ``name`` rolls up: the registry's ``rollup``, else by direction
    (lower -> sum, higher -> min, the conservative choice), else none."""
    from .registry import lookup
    reg = lookup(name) or {}
    if reg.get("rollup") in RULES:
        return reg["rollup"]
    b = better or reg.get("better") or "none"
    return _BY_BETTER.get(b, "none")


def _sig(v):
    # Significant digits, not fixed decimals: simulated time is routinely
    # 1e-6 s (matches libhdlsim's sim_stats.aggregate).
    return float("%.6g" % v)


def rollup_metrics(children, detail: bool = False):
    """Metrics of a parent over its children's metrics, per name.

    ``detail`` adds the spread the way libhdlsim's suite ``stats`` always has:
    a summed metric also gets ``<name>_max`` and ``<name>_mean``, and a
    max-rolled one is reported only as ``<name>_max``."""
    acc = {}
    order = []
    for c in children:
        for name, m in (_get(c, "metrics") or {}).items():
            v, unit, better, label = _metric_parts(m)
            if v is None:
                continue
            if name not in acc:
                acc[name] = {"vals": [], "unit": unit, "better": better, "label": label}
                order.append(name)
            a = acc[name]
            a["vals"].append(v)
            for k, x in (("unit", unit), ("better", better), ("label", label)):
                if a[k] is None and x is not None:
                    a[k] = x

    out = {}
    for name in order:
        a = acc[name]
        vals = a["vals"]
        rule = metric_rule(name, a["better"])

        def mk(v, nm=name):
            m = {"value": _sig(v) if detail else v}
            if a["unit"]:
                m["unit"] = a["unit"]
            if a["better"]:
                m["better"] = a["better"]
            if a["label"] and nm == name:
                m["label"] = a["label"]
            return m
        if rule == "sum":
            out[name] = mk(sum(vals))
            if detail:
                out[name + "_max"] = mk(max(vals), name + "_max")
                out[name + "_mean"] = mk(sum(vals) / len(vals), name + "_mean")
        elif rule == "max":
            out[(name + "_max") if detail else name] = mk(max(vals), name + "_max" if detail else name)
        elif rule == "min":
            out[name] = mk(min(vals))
        elif rule == "mean":
            out[name] = mk(sum(vals) / len(vals))
    return out


def rollup(children, detail: bool = False):
    """``(status, counts, metrics)`` of a parent over ``children``: the worst
    child status (``notrun`` when there are none), leaf counts, and metrics
    per ``rollup_metrics``."""
    from .status import worst_of
    kids = list(children)
    status = worst_of([_get(c, "status") or "pass" for c in kids],
                      "notrun")
    return status, leaf_counts(kids), rollup_metrics(kids, detail)
