#****************************************************************************
#* result_collect.py -- std.ResultCollect, and the std.TestSuite / std.TestRunner roll-ups
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
"""Aggregate the ``std.Result`` items among a task's inputs into one node.

``std.ResultCollect`` is domain-neutral: it groups a test run, a synthesis
run and a formal run under one verdict as readily as it groups test cases.
``std.TestSuite`` and ``std.TestRunner`` use the same code to emit a
``std.SuiteResult`` / ``std.TestRunResult`` over their members.
"""
from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.results import api as R
from dv_flow.mgr.results.collect import runtime_resolver, top_results
from dv_flow.mgr.results.rollup import rollup


def collect(ctxt, inputs, type="std.Result", name="", checks=None,
            empty_ok=True, task=None):
    """The roll-up node over the top Result items in ``inputs``, or None when
    there are none and ``empty_ok`` is False."""
    kids = top_results(inputs, runtime_resolver(ctxt))
    if not kids and not empty_ok:
        return None
    node = R.mk_result(ctxt, type, name=name)
    if task:
        node.task = task
    node.children = list(kids)
    status, counts, metrics = rollup(kids)
    node.counts = counts
    node.metrics = metrics
    if not kids:
        node.status = "notrun"
        node.msg = "no results"
    else:
        node.status = status
    # A check may read a roll-up metric or a leaf count (`fail`, `total` ...)
    values = dict(metrics)
    for k, v in counts.items():
        values.setdefault(k, {"value": v})
    for c in checks or []:
        c = dict(c)
        if c.get("metric") and c.get("op"):
            node.checks.append(R.eval_check(values, c.get("name") or c["metric"],
                                            c["metric"], c["op"], c.get("goal"), c.get("msg")))
        else:
            node.checks.append(R.check(c.get("name", "check"), c.get("status", "error"),
                                       msg=c.get("msg") or "check needs metric and op"))
    if hasattr(node, "total"):
        node.total = counts.get("total", 0)
        node.failed = counts.get("fail", 0)
        node.errored = counts.get("error", 0) + counts.get("timeout", 0)
    R.finish(node)
    if kids and not node.msg:
        from dv_flow.mgr.results.summary import count_msg
        node.msg = count_msg(counts)
    return node


async def ResultCollect(ctxt, input) -> TaskDataResult:
    p = input.params
    node = collect(ctxt, input.inputs, type=getattr(p, "type", "") or "std.Result",
                   name=getattr(p, "name", "") or "", checks=getattr(p, "checks", None) or [])
    return TaskDataResult(output=[node])


async def TestSuiteRun(ctxt, input) -> TaskDataResult:
    """A `std.TestSuite`: its members pass through (as before), plus a
    `std.SuiteResult` over the ones that report a Result."""
    node = collect(ctxt, input.inputs, type="std.SuiteResult", empty_ok=False)
    return TaskDataResult(output=[node] if node is not None else [])


async def TestRunnerRun(ctxt, input) -> TaskDataResult:
    """A `std.TestRunner`: its inputs pass through (as before), plus a
    `std.TestRunResult` over the Results among them."""
    node = collect(ctxt, input.inputs, type="std.TestRunResult", empty_ok=False)
    return TaskDataResult(output=[node] if node is not None else [])
