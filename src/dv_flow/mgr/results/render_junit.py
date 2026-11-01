#****************************************************************************
#* render_junit.py -- results.json as JUnit XML and CTRF
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
"""JUnit XML and CTRF renderings of a run record. Pure: a ``ResultsFile``
in, text out.

The mapping is the same for both, and it is the one place that knows the
test profile:

* a ``std.TestResult`` node is a test case;
* a ``std.SuiteResult`` node groups the cases under it (flattened to one
  JUnit ``testsuite`` per suite, named by its path);
* any other node with checks -- a synthesis run, a coverage goal -- is a
  suite with **one test case per check**, so ``synth/timing`` fails in CI
  next to the test failures; its children are details and are not
  repeated;
* any other leaf is a suite with one case named after it; other parents
  (``_tasks``, a ``std.ResultCollect`` group) are walked through.

A test case's scalar ``attrs`` and its metric values are JUnit
``<properties>`` and CTRF ``extra`` keys. A failure carries ``msg`` and the
failing checks; ``error`` and ``timeout``
are JUnit errors; ``skip`` and ``notrun`` are skipped, with ``notrun``'s
message naming what blocked it.
"""
import time
import uuid
from typing import List, Tuple
from xml.sax.saxutils import escape, quoteattr

from .model import ResultNode, ResultsFile
from .summary import first_artifact, log_ref
from .render_text import fmt_check, fmt_value

CTRF_SPEC_VERSION = "0.0.0"


class Case(object):
    __slots__ = ("suite", "name", "classname", "status", "msg", "details",
                 "time_s", "log", "metrics", "node")

    def __init__(self, suite, name, classname, status, msg="", details=(),
                 time_s=None, log=None, metrics=None, node=None):
        self.suite, self.name, self.classname = suite, name, classname
        self.status, self.msg, self.details = status, msg, list(details)
        self.time_s, self.log, self.metrics, self.node = time_s, log, metrics or {}, node


def _is(node, t):
    return t in node.types


def _time(node):
    m = node.metrics.get("walltime_s")
    return m.value if m is not None else None


def _log(node):
    lr = log_ref(node)
    if lr is None:
        return None
    return "%s%s" % (lr["path"], (":%d" % lr["line"]) if lr.get("line") else "")


def _details(node):
    return [fmt_check(c) for c in node.checks if c.status in ("fail", "error")]


def cases(rf: ResultsFile) -> List[Case]:
    """The run as a flat list of test cases (in tree order)."""
    out = []

    def case_of(node, suite, path):
        return Case(suite, node.name or "?", path, node.status, node.msg, _details(node),
                    _time(node), _log(node), node.metrics, node)

    def visit(node: ResultNode, path: str, suite: str):
        if _is(node, "std.TestResult"):
            out.append(case_of(node, suite or path.rsplit("/", 1)[0] or path, path))
            return
        if _is(node, "std.SuiteResult"):
            for c in node.children:
                visit(c, path + "/" + (c.name or "?"), path)
            return
        if node.checks:
            for ck in node.checks:
                st = ck.status if ck.status in ("pass", "fail", "error", "skip") else "error"
                msg = (node.msg if st != "pass" else "") or ""
                out.append(Case(path, ck.name, path, st, msg,
                                [fmt_check(ck)] if st in ("fail", "error") else [],
                                _time(node) if ck is node.checks[0] else None,
                                _log(node), {}, node))
            return
        if node.children:
            for c in node.children:
                visit(c, path + "/" + (c.name or "?"), "")
            return
        out.append(Case(path, node.name or "?", path, node.status, node.msg,
                        _details(node), _time(node), _log(node), node.metrics, node))

    root = rf.result
    visit(root, root.name or "run", "")
    return out


def _scalar(v):
    return isinstance(v, (str, int, float, bool)) and v != ""


def properties(c: Case):
    """(name, value) pairs for a case: the node's scalar `attrs` (the
    reproduction handles a producer records: sim, seed, host ...) and its
    metric values with their unit (`608us`). JUnit's `<properties>` and CTRF's `extra` carry them."""
    if c.node is None or not _is(c.node, "std.TestResult"):
        return []
    props = [(k, v) for k, v in c.node.attrs.items() if _scalar(v)]
    props += [(k, fmt_value(m.value) + (m.unit or "")) for k, m in c.metrics.items()]
    return props


def _group(cs):
    order, by = [], {}
    for c in cs:
        if c.suite not in by:
            by[c.suite] = []
            order.append(c.suite)
        by[c.suite].append(c)
    return [(s, by[s]) for s in order]


def _kind(st):
    if st == "fail":
        return "failure"
    if st in ("error", "timeout"):
        return "error"
    if st in ("skip", "notrun"):
        return "skipped"
    return None


def render_junit(rf: ResultsFile) -> str:
    cs = cases(rf)
    groups = _group(cs)

    def counts(lst):
        return (len(lst), sum(1 for c in lst if _kind(c.status) == "failure"),
                sum(1 for c in lst if _kind(c.status) == "error"),
                sum(1 for c in lst if _kind(c.status) == "skipped"))

    t, f, e, s = counts(cs)
    root = rf.run.root if isinstance(rf.run.root, str) else ",".join(rf.run.root)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<testsuites name=%s tests="%d" failures="%d" errors="%d" skipped="%d">' % (
                 quoteattr(root), t, f, e, s)]
    for suite, lst in groups:
        t, f, e, s = counts(lst)
        lines.append('  <testsuite name=%s tests="%d" failures="%d" errors="%d" skipped="%d">' % (
            quoteattr(suite), t, f, e, s))
        for c in lst:
            attrs = 'name=%s classname=%s' % (quoteattr(c.name), quoteattr(c.classname))
            if c.time_s is not None:
                attrs += ' time="%s"' % fmt_value(round(c.time_s, 3))
            body = []
            props = properties(c)
            if props:
                body.append('      <properties>')
                for k, v in props:
                    body.append('        <property name=%s value=%s/>' % (
                        quoteattr(str(k)), quoteattr(str(v))))
                body.append('      </properties>')
            kind = _kind(c.status)
            if kind is not None:
                msg = "%s: %s" % (c.status, c.msg) if c.msg else c.status
                text = "\n".join(c.details)
                if text:
                    body.append('      <%s message=%s>%s</%s>' % (kind, quoteattr(msg), escape(text), kind))
                else:
                    body.append('      <%s message=%s/>' % (kind, quoteattr(msg)))
            if c.log:
                body.append('      <system-out>%s</system-out>' % escape("log: " + c.log))
            if body:
                lines.append('    <testcase %s>' % attrs)
                lines.extend(body)
                lines.append('    </testcase>')
            else:
                lines.append('    <testcase %s/>' % attrs)
        lines.append('  </testsuite>')
    lines.append('</testsuites>')
    return "\n".join(lines) + "\n"


_CTRF_STATUS = {"pass": "passed", "fail": "failed", "error": "failed",
                "timeout": "failed", "skip": "skipped", "notrun": "skipped"}


def _iso_ms(text):
    import datetime
    if not text:
        return None
    try:
        return int(datetime.datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None


def ctrf_doc(rf: ResultsFile, report_id: str = None):
    """The CTRF report as a dict (the spec version libhdlsim's writer uses).
    ``extra`` carries each case's metrics and its raw status."""
    tests = []
    for c in cases(rf):
        t = {"name": c.name, "status": _CTRF_STATUS.get(c.status, "other"),
             "rawStatus": c.status,
             "duration": int(round((c.time_s or 0) * 1000)),
             "suite": c.suite}
        msg = c.msg
        if c.details:
            msg = (msg + "; " if msg else "") + "; ".join(c.details)
        if msg:
            t["message"] = msg
        extra = {}
        if c.node is not None and _is(c.node, "std.TestResult"):
            extra.update({k: v for k, v in c.node.attrs.items() if _scalar(v)})
            extra.update({k: m.value for k, m in c.metrics.items()})
        if c.log:
            extra["log"] = c.log
        if c.node is not None and c.node.task:
            extra["task"] = c.node.task
        if extra:
            t["extra"] = extra
        tests.append(t)
    summary = {"tests": len(tests), "passed": 0, "failed": 0, "skipped": 0,
               "pending": 0, "other": 0}
    for t in tests:
        summary[t["status"]] += 1
    now = int(time.time() * 1000)
    summary["start"] = _iso_ms(rf.run.start_time) or now
    summary["stop"] = _iso_ms(rf.run.end_time) or summary["start"]
    return {
        "reportFormat": "CTRF",
        "specVersion": CTRF_SPEC_VERSION,
        "reportId": report_id or str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(summary["start"] / 1000.0)),
        "generatedBy": "dv-flow-mgr",
        "results": {
            "tool": {"name": "dfm"},
            "summary": summary,
            "tests": tests,
            "extra": {"run": rf.run.id, "status": rf.summary.status},
        },
    }


def render_ctrf(rf: ResultsFile, report_id: str = None) -> str:
    import json
    return json.dumps(ctrf_doc(rf, report_id), indent=2) + "\n"
