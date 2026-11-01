#****************************************************************************
#* api.py -- helpers for tasks that produce a std.Result
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
"""Helpers for task authors who produce a ``std.Result``.

A minimal pytask::

    from dv_flow.mgr.results import api as R

    async def Lint(ctxt, input):
        ...  # run the tool, count warnings
        res = R.mk_result(ctxt, name="lint", metrics={"warnings": R.metric(n)})
        res.checks.append(R.eval_check(res.metrics, "clean", "warnings", "<=", 0))
        res.artifacts.append(R.artifact(ctxt, "lint.log", role="log"))
        R.finish(res)
        return TaskDataResult(output=[res])     # status 0: failure is data

The helpers work on a data item made by ``ctxt.mkDataItem`` or on a plain
dict with the same fields.
"""
import operator
import os
from typing import Any, Dict, Optional

from .convert import SEV_COUNT_KEY, as_dict, convert_diagnostic, norm_severity
from .status import worst, worst_of

_OPS = {
    ">=": operator.ge, "<=": operator.le, "==": operator.eq,
    "!=": operator.ne, ">": operator.gt, "<": operator.lt,
}


def _get(obj, key, dflt=None):
    if isinstance(obj, dict):
        return obj.get(key, dflt)
    return getattr(obj, key, dflt)


def _set(obj, key, value):
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def mk_result(ctxt, type: str = "std.Result", name: str = "", **kw):
    """Make a Result data item of ``type`` (any ``std.Result`` subtype).
    ``task`` and ``rundir`` default to the calling task's."""
    item = ctxt.mkDataItem(type)
    # mkDataItem consumes a `name` keyword without setting it; set fields here.
    task = getattr(ctxt, "name", "") or ""
    _set(item, "name", name or task.rsplit(".", 1)[-1])
    if task and not kw.get("task"):
        _set(item, "task", task)
    if getattr(ctxt, "rundir", None) and not kw.get("rundir"):
        _set(item, "rundir", ctxt.rundir)
    for k, v in kw.items():
        _set(item, k, v)
    return item


def metric(value, unit: Optional[str] = None, better: Optional[str] = None,
           label: Optional[str] = None, *, name: Optional[str] = None) -> Dict[str, Any]:
    """A Metric map. With ``name``, the unit, direction and label default to
    the std metric registry's entry for that name (when it has one)."""
    m = {"value": float(value)}
    reg = None
    if name is not None:
        from .registry import lookup
        reg = lookup(name)
    if unit is None and reg is not None:
        unit = reg.get("unit")
    if better is None and reg is not None:
        better = reg.get("better")
    if label is None and reg is not None:
        label = reg.get("label")
    if unit:
        m["unit"] = unit
    if better:
        m["better"] = better
    if label:
        m["label"] = label
    return m


def check(name: str, status: str, metric: Optional[str] = None,
          op: Optional[str] = None, goal=None, msg: Optional[str] = None,
          value=None) -> Dict[str, Any]:
    """A ResultCheck map with a status the caller decided."""
    c = {"name": name, "status": status}
    if metric is not None:
        c["metric"] = metric
    if op is not None:
        c["op"] = op
        c["goal"] = goal
    if value is not None:
        c["value"] = value
    if msg:
        c["msg"] = msg
    return c


def _metric_value(metrics, name):
    v = (metrics or {}).get(name) if isinstance(metrics, dict) else None
    if isinstance(v, dict):
        v = v.get("value")
    elif v is not None and hasattr(v, "value"):
        v = v.value
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v


def eval_check(metrics, name: str, metric: str, op: str, goal,
               msg: Optional[str] = None) -> Dict[str, Any]:
    """A ResultCheck whose status is computed: ``metrics[metric] op goal``.
    A metric that was not reported, or an unknown op, gives ``error``."""
    fn = _OPS.get(op)
    if fn is None:
        return check(name, "error", metric, op, goal,
                     msg or "unknown check operator '%s'" % op)
    v = _metric_value(metrics, metric)
    if v is None:
        return check(name, "error", metric, op, goal,
                     msg or "metric '%s' not reported" % metric)
    try:
        ok = fn(v, goal)
    except TypeError:
        return check(name, "error", metric, op, goal, value=v,
                     msg=msg or "cannot compare %s %s %r" % (metric, op, goal))
    return check(name, "pass" if ok else "fail", metric, op, goal, msg=msg, value=v)


def diagnostic_from_marker(m, category: str = "tool") -> Dict[str, Any]:
    """A TaskMarker as a Diagnostic map."""
    d = convert_diagnostic(m)
    d.setdefault("category", category)
    return d


def artifact(ctxt, path: str, role: str, filetype: Optional[str] = None,
             label: Optional[str] = None, **attrs):
    """A ``std.FileSet`` for one file with ``role=`` (and ``label=``)
    attributes. A relative ``path`` is resolved against the task's rundir."""
    from ..fileset import FileSet
    if not os.path.isabs(path) and ctxt is not None and getattr(ctxt, "rundir", None):
        path = os.path.join(ctxt.rundir, path)
    a = ["role=%s" % role]
    if label:
        a.append("label=%s" % label)
    for k, v in attrs.items():
        a.append("%s=%s" % (k, v))
    kw = {}
    src = getattr(ctxt, "name", None) if ctxt is not None else None
    if src:
        kw["src"] = src
    return FileSet(filetype=filetype or role, basedir=os.path.dirname(path),
                   files=[os.path.basename(path)], attributes=a, **kw)


_FIXED = ("error", "timeout", "skip", "notrun")


def _fmt_goal(c):
    m = c.get("metric")
    if m and c.get("op"):
        v = c.get("value")
        vs = ("%g" % v) if isinstance(v, (int, float)) else "?"
        return "%s=%s, want %s %s" % (m, vs, c["op"], c.get("goal"))
    return ""


def finish(result):
    """Derive the verdict from the checks (and children), then ``passed``
    and ``counts``. Returns ``result``.

    * The status is the worst of the explicit status (``pass`` if unset) and
      every non-skipped check (and child): a failing check fails the node,
      a passing check never clears an explicit ``fail``/``error``.
    * ``passed`` is ``status == "pass"``.
    * ``counts`` gets diagnostic totals by severity and, for a node with
      children, leaf-status totals, unless the producer set them.
    * An empty ``msg`` on a failing node names the first failing check.
    """
    checks = [as_dict(c) for c in (_get(result, "checks") or [])]
    children = list(_get(result, "children") or [])
    st = _get(result, "status") or "pass"
    st = worst(st, worst_of([c.get("status") for c in checks
                             if c.get("status") not in (None, "skip")]))
    child_st = [_get(c, "status") or "pass" for c in children]
    st = worst(st, worst_of(child_st))
    _set(result, "status", st)
    _set(result, "passed", st == "pass")

    counts = dict(_get(result, "counts") or {})
    dcounts = {}
    for dg in _get(result, "diagnostics") or []:
        key = SEV_COUNT_KEY[norm_severity(_get(dg, "severity"))]
        dcounts[key] = dcounts.get(key, 0) + 1
    for k, v in dcounts.items():
        counts.setdefault(k, v)
    if children:
        from .rollup import leaf_counts
        for k, v in leaf_counts(children).items():
            counts.setdefault(k, v)
    _set(result, "counts", counts)

    if st != "pass" and not _get(result, "msg"):
        for c in checks:
            if c.get("status") in ("fail", "error"):
                detail = c.get("msg") or _fmt_goal(c)
                _set(result, "msg", "check %s %s%s" % (
                    c.get("name"), "failed" if c["status"] == "fail" else "errored",
                    (": " + detail) if detail else ""))
                break
    return result


def artifacts(inputs, role: Optional[str] = None, filetype: Optional[str] = None,
              resolve=None):
    """The artifact FileSets of the Result trees among ``inputs`` (a task's
    `input.inputs`), each stamped with where it came from: the attributes
    gain ``result_path=<path in the tree>`` and, when the result says,
    ``testname=`` and ``seed=``. ``role`` / ``filetype`` filter (a legacy
    role name -- ``trace``, ``stats`` -- matches its std name).

    This is how a task downstream of a root reaches files: through the
    Result, so each one arrives with the identity and verdict of the result
    that produced it (a coverage merge knows which test each database came
    from).
    """
    from ..fileset import FileSet
    from .collect import top_results
    from .convert import LEGACY_ROLES, attr_map

    want_role = LEGACY_ROLES.get(role, role) if role else None
    out = []
    seen = set()

    def visit(node, path):
        d = as_dict(node)
        name = d.get("name") or "?"
        here = (path + "/" + name) if path else name
        attrs = d.get("attrs") if isinstance(d.get("attrs"), dict) else {}
        testname = d.get("testname") or attrs.get("testname")
        seed = d.get("seed") if d.get("seed") not in (None, "", 0) else attrs.get("seed")
        for a in d.get("artifacts") or []:
            ad = as_dict(a)
            am = attr_map(ad.get("attributes"))
            r = LEGACY_ROLES.get(am.get("role"), am.get("role")) or "other"
            if want_role and r != want_role:
                continue
            if filetype and ad.get("filetype") != filetype:
                continue
            key = (ad.get("basedir"), tuple(ad.get("files") or []))
            if key in seen:
                continue
            seen.add(key)
            extra = ["result_path=%s" % here]
            if testname:
                extra.append("testname=%s" % testname)
            if seed not in (None, ""):
                extra.append("seed=%s" % seed)
            keep = [x for x in (ad.get("attributes") or [])
                    if not str(x).split("=", 1)[0] in ("result_path", "testname", "seed")]
            kw = {}
            if ad.get("src"):
                kw["src"] = ad["src"]
            out.append(FileSet(filetype=ad.get("filetype") or "", basedir=ad.get("basedir") or "",
                               files=list(ad.get("files") or []),
                               incdirs=list(ad.get("incdirs") or []),
                               defines=list(ad.get("defines") or []),
                               attributes=keep + extra, **kw))
        for c in (d.get("children") or d.get("results") or []):
            visit(c, here)

    for item in top_results(inputs, resolve):
        visit(item, "")
    return out
