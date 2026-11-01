#****************************************************************************
#* convert.py -- std.Result data item -> ResultNode
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
"""Turn a ``std.Result`` data item (a pydantic item, a namespace or a plain
dict) into a ``ResultNode``, following the format rules:

* ``type``/``types`` carry the item's is-a lineage, cut at ``std.Result``.
* ``status`` is normalized. An unknown value becomes ``error`` (with a
  warning); an empty one is derived from the checks, then the children, then
  ``passed``. ``passed`` is always ``status == "pass"``.
* Bare-number metrics become ``Metric`` maps. Non-numeric values move to
  ``attrs``.
* Legacy artifact roles map: ``trace`` -> ``waves``, ``stats`` -> ``data``.
* Diagnostics are capped at ``max_diags`` (most severe first, stable).
  ``counts`` keeps the true totals by severity (``errors``, ``warnings``,
  ``fatals``, ``infos``).
* Unknown fields are kept (``extra="allow"``). ``seq`` is dropped and the
  data item's ``src`` fills ``task`` when the item has none.
"""
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from .lineage import type_lineage
from .model import ResultNode
from .status import CHECK_STATUSES, is_status, worst_of

_log = logging.getLogger("results.convert")

MAX_DIAGS = 10

LEGACY_ROLES = {"trace": "waves", "stats": "data"}

_SEV_RANK = {"fatal": 0, "error": 1, "warning": 2, "info": 3}
_SEV_ALIASES = {"warn": "warning", "err": "error", "note": "info",
                "information": "info", "critical": "fatal"}
SEV_COUNT_KEY = {"fatal": "fatals", "error": "errors",
                  "warning": "warnings", "info": "infos"}

# Fields of the node itself; everything else is an extra.
_CORE = {"name", "type", "types", "status", "passed", "msg", "task", "rundir",
         "tool", "attrs", "metrics", "checks", "counts", "diagnostics",
         "artifacts", "children", "start_time", "end_time", "reused"}
_DROP = {"seq", "src"}


def as_dict(item) -> Dict[str, Any]:
    """A data item (pydantic model, namespace, dict) as a plain dict."""
    if item is None:
        return {}
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        try:
            return item.model_dump(warnings=False)
        except TypeError:
            return item.model_dump()
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    return {}


def attr_map(attributes) -> Dict[str, str]:
    """``["role=log", "label=Timing"]`` -> ``{"role": "log", "label": "Timing"}``."""
    ret = {}
    for a in attributes or []:
        if isinstance(a, str) and "=" in a:
            k, v = a.split("=", 1)
            ret.setdefault(k.strip(), v.strip())
    return ret


def norm_role(role) -> str:
    if not role:
        return "other"
    return LEGACY_ROLES.get(role, role)


def norm_severity(sev) -> str:
    if sev is None:
        return "error"
    if hasattr(sev, "value"):          # SeverityE
        sev = sev.value
    s = str(sev).strip().lower()
    s = _SEV_ALIASES.get(s, s)
    return s if s in _SEV_RANK else "error"


def _num(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def convert_artifact(fs) -> Dict[str, Any]:
    d = as_dict(fs)
    attrs = attr_map(d.get("attributes"))
    role = norm_role(d.get("role") or attrs.get("role"))
    ret = {
        "type": d.get("type") or "std.FileSet",
        "filetype": d.get("filetype") or "",
        "basedir": d.get("basedir") or "",
        "files": list(d.get("files") or []),
        "attributes": [a for a in (d.get("attributes") or []) if isinstance(a, str)],
        "role": role,
    }
    label = d.get("label") or attrs.get("label")
    if label:
        ret["label"] = label
    if d.get("stamps"):
        ret["stamps"] = d["stamps"]
    for k in ("src", "name"):
        if d.get(k):
            ret[k] = d[k]
    return ret


def convert_diagnostic(m, log_path=None) -> Dict[str, Any]:
    """A TaskMarker, an older library's diagnostic map (message, log_line,
    file/line) or a Diagnostic map -> Diagnostic."""
    d = as_dict(m)
    ret = {"severity": norm_severity(d.get("severity")),
           "msg": str(d.get("msg") or d.get("message") or "")}
    for k in ("category", "time", "hier", "code"):
        if d.get(k) not in (None, ""):
            ret[k] = str(d[k]) if k != "code" else d[k]

    loc = as_dict(d.get("loc")) if d.get("loc") is not None else {}
    loc = {k: v for k, v in loc.items() if v not in (None, "", -1)}
    if "log_line" in d and d["log_line"] not in (None, ""):
        loc.setdefault("line", d["log_line"])
    if loc and not loc.get("path") and log_path:
        loc["path"] = log_path
    if loc:
        ret["loc"] = loc

    src = as_dict(d.get("src_loc")) if d.get("src_loc") is not None else {}
    if not src and d.get("file"):
        src = {"path": d["file"]}
        if d.get("line") not in (None, ""):
            src["line"] = d["line"]
    src = {k: v for k, v in src.items() if v not in (None, "", -1)}
    if src:
        ret["src_loc"] = src
    return ret


def cap_diagnostics(diags, max_diags=MAX_DIAGS):
    """(kept, counts): the most severe first (stable), and totals by severity."""
    counts = {}
    for dg in diags:
        key = SEV_COUNT_KEY[dg["severity"]]
        counts[key] = counts.get(key, 0) + 1
    order = sorted(range(len(diags)), key=lambda i: (_SEV_RANK[diags[i]["severity"]], i))
    return [diags[i] for i in order[:max_diags]], counts


def convert_metric(name, v):
    """(metric map | None, attr value | None)."""
    n = _num(v)
    if n is not None:
        return {"value": n}, None
    if isinstance(v, dict) and _num(v.get("value")) is not None:
        m = {"value": float(v["value"])}
        if v.get("unit"):
            m["unit"] = str(v["unit"])
        if v.get("better") in ("higher", "lower", "none"):
            m["better"] = v["better"]
        if v.get("label"):
            m["label"] = str(v["label"])
        for k, x in v.items():
            if k not in ("value", "unit", "better", "label"):
                m[k] = x
        return m, None
    return None, v


def convert_check(c, warnings) -> Dict[str, Any]:
    d = as_dict(c)
    st = str(d.get("status") or "").strip().lower()
    if st not in CHECK_STATUSES:
        warnings.append("check '%s' has status '%s'" % (d.get("name"), d.get("status")))
        st = "error"
    ret = {"name": str(d.get("name") or "check"), "status": st}
    for k in ("metric", "op", "msg"):
        if d.get(k) not in (None, ""):
            ret[k] = str(d[k])
    if d.get("goal") is not None and "op" in ret:
        ret["goal"] = d["goal"]
    if _num(d.get("value")) is not None:
        ret["value"] = float(d["value"])
    return ret


def to_dict(item, resolve: Callable = None, max_diags: int = MAX_DIAGS,
            warnings: Optional[List[str]] = None, _path="") -> Dict[str, Any]:
    """Convert to a plain dict in ResultNode shape (see ``to_node``)."""
    if warnings is None:
        warnings = []
    d = as_dict(item)
    typ = d.get("type") or "std.Result"
    ret: Dict[str, Any] = {
        "name": str(d.get("name") or ""),
        "type": typ,
        "types": type_lineage(typ, resolve),
    }
    path = (_path + "/" + ret["name"]) if _path else (ret["name"] or "<root>")

    for k in ("msg", "task", "rundir", "start_time", "end_time"):
        if d.get(k) not in (None, ""):
            ret[k] = str(d[k])
    if not ret.get("task") and d.get("src"):
        ret["task"] = str(d["src"])
    ret["reused"] = bool(d.get("reused") or False)
    if isinstance(d.get("tool"), dict) and d["tool"]:
        ret["tool"] = dict(d["tool"])
    attrs = dict(d["attrs"]) if isinstance(d.get("attrs"), dict) else {}

    # Metrics
    metrics = {}
    for k, v in (d.get("metrics") or {}).items():
        m, a = convert_metric(k, v)
        if m is not None:
            metrics[k] = m
        elif a is not None:
            attrs.setdefault(k, a)
    ret["metrics"] = metrics
    if attrs:
        ret["attrs"] = attrs

    ret["checks"] = [convert_check(c, warnings) for c in (d.get("checks") or [])]

    # Artifacts (first, so diagnostics can point into the log)
    arts = [convert_artifact(a) for a in (d.get("artifacts") or [])]
    ret["artifacts"] = arts
    log_path = None
    for a in arts:
        if a["role"] == "log" and a["files"]:
            log_path = os.path.join(a["basedir"], a["files"][0]) if a["basedir"] else a["files"][0]
            break

    diags = [convert_diagnostic(x, log_path) for x in (d.get("diagnostics") or [])]
    kept, dcounts = cap_diagnostics(diags, max_diags)
    ret["diagnostics"] = kept
    counts = {}
    for k, v in (d.get("counts") or {}).items():
        if _num(v) is not None:
            counts[k] = int(v)
    for k, v in dcounts.items():
        counts.setdefault(k, v)
    ret["counts"] = counts

    # Children (`results` is an older libraries' spelling of `children`)
    kids = d.get("children")
    extras_skip = set()
    if not kids and isinstance(d.get("results"), list) and d["results"]:
        kids = d["results"]
        extras_skip.add("results")
    ret["children"] = [to_dict(c, resolve, max_diags, warnings, path) for c in (kids or [])]

    # Status
    raw = d.get("status")
    st = str(raw).strip().lower() if raw not in (None, "") else ""
    if st and not is_status(st):
        warnings.append("%s: unknown status '%s'; recorded as error" % (path, raw))
        if not ret.get("msg"):
            ret["msg"] = "invalid result status '%s'" % raw
        st = "error"
    if not st:
        if ret["checks"]:
            st = worst_of([c["status"] for c in ret["checks"] if c["status"] != "skip"], "pass")
        elif ret["children"]:
            st = worst_of([c["status"] for c in ret["children"]], "pass")
        elif isinstance(d.get("passed"), bool):
            st = "pass" if d["passed"] else "fail"
        else:
            warnings.append("%s: result has no status; recorded as error" % path)
            if not ret.get("msg"):
                ret["msg"] = "result has no status"
            st = "error"
    ret["status"] = st
    ret["passed"] = (st == "pass")

    # Extras
    for k, v in d.items():
        if k in _CORE or k in _DROP or k in extras_skip:
            continue
        if k == "passed":
            continue
        ret[k] = v
    if "passed" in d and not isinstance(d["passed"], bool) and _num(d["passed"]) is not None:
        ret["npassed"] = int(d["passed"])
    return ret


def to_node(item, resolve: Callable = None, max_diags: int = MAX_DIAGS,
            warnings: Optional[List[str]] = None) -> ResultNode:
    """Convert a ``std.Result`` data item into a ``ResultNode``.

    ``resolve(name) -> Type`` is the type registry lookup used for lineage
    (``loader.findType``). Problems that were repaired (an unknown status)
    are appended to ``warnings``.
    """
    return ResultNode.model_validate(to_dict(item, resolve, max_diags, warnings))
