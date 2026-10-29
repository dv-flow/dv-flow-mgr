#****************************************************************************
#* task_listener_events.py -- runner events as protocol lines (event_sink.py)
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
"""A detail listener (``TaskRunner.add_event_listener``) that turns runner
notifications into the event protocol:

- ``run.start``    the outermost runner's ``start``: origin, roots, jobs
- ``graph.plan``   the outermost runner's ``plan``: every node it will run
- ``graph.extend`` dynamic sub-graphs and nested runners: the nodes they add
- ``task.state``   ``enter``, ``checking``, ``run``, ``uptodate``,
                   ``cache_hit``, ``base_hit``, ``done`` (from ``leave``) and
                   ``skipped``
- ``task.marker``  as each marker is added, and at ``done`` for markers the
                   task returned in its result
- ``task.exec``    each command's start and end
- ``run.alive``    the heartbeat, after a quiet interval: what is running
- ``run.end``      the outermost runner's ``end`` (sent by ``close``)

Node ids are fully-qualified task names. A second node object with a name
already in use (a loop body run again) gets ``#2``, ``#3`` and so on.
"""
import os
from typing import Any, Dict, List, Optional
from .event_sink import EventEmitter

_STATES = ("enter", "checking", "run", "uptodate", "cache_hit", "base_hit")

MSG_MAX = 2000
ALIVE_MAX_IDS = 32
CMD_MAX_ARGS = 32
CMD_MAX_CHARS = 1024


class TaskListenerEvents(object):

    def __init__(self, emitter: EventEmitter, roots: Optional[List[str]] = None,
                 rundir: Optional[str] = None):
        self.emitter = emitter
        self.roots = list(roots) if roots else []
        self.rundir = rundir
        self._depth = 0
        self._runner = None
        self._ids: Dict[int, str] = {}       # id(node) -> node id
        self._keep: List[Any] = []           # keep nodes alive, so id() stays unique
        self._names: Dict[str, int] = {}     # name -> times used
        self._sent: set = set()              # id(node) of nodes already in a plan/extend
        self._markers: Dict[str, set] = {}   # node id -> id() of markers sent
        self._counts: Dict[str, int] = {}
        self._running: Dict[str, None] = {}  # node ids entered, not yet done (ordered)
        self._ended = False

    # The callable registered with add_event_listener
    def event(self, subject, reason: str, info=None):
        if reason == "start":
            self._depth += 1
            if self._depth == 1:
                self._runner = subject
                self._start(subject)
        elif reason == "end":
            self._depth -= 1
            if self._depth == 0:
                self.close(subject)
        elif reason == "plan":
            nodes = self._nodes(info["dep_map"])
            if self._depth <= 1 and subject is self._runner:
                self.emitter.emit("graph.plan", nodes=nodes)
            elif nodes:
                # A nested runner (input update, sub-graph fallback)
                self.emitter.emit("graph.extend", scope=None, nodes=nodes)
        elif reason == "extend":
            nodes = self._nodes(info["dep_map"])
            if nodes:
                self.emitter.emit("graph.extend", scope=info.get("scope"), nodes=nodes)
        elif reason in _STATES:
            nid = self._id(subject)
            if reason == "enter":
                self._running[nid] = None
            self.emitter.emit("task.state", id=nid, state=reason)
        elif reason == "leave":
            self._done(subject)
        elif reason == "skipped":
            self._counts["skipped"] = self._counts.get("skipped", 0) + 1
            nid = self._id(subject)
            self._running.pop(nid, None)
            self.emitter.emit("task.state", id=nid, state="skipped")
        elif reason == "marker":
            self._marker(subject, info)
        elif reason == "exec":
            self._exec(subject, info)

    def close(self, runner=None):
        """Send ``run.end`` and shut the emitter down. Safe to call more than
        once; cmd_run calls it again after the run, in case the runner raised
        before its ``end``."""
        if self._ended:
            return
        self._ended = True
        runner = runner if runner is not None else self._runner
        status = getattr(runner, "status", None)
        if self._depth > 0 or runner is None:
            result = "error"
        else:
            result = "ok" if status == 0 else "fail"
        self.emitter.close("run.end", status=status, result=result,
                           counts=dict(self._counts))

    def _start(self, runner):
        o = self.emitter.origin()
        rundir = self.rundir or getattr(runner, "rundir", None)
        o["rundir"] = os.path.abspath(rundir) if rundir else None
        o["dfm_run_id"] = self._run_id(runner)
        o["roots"] = self.roots
        o["jobs"] = getattr(runner, "nproc", None)
        self.emitter.emit("run.start", **o)
        self.emitter.start_heartbeat(self._alive)

    def _alive(self):
        """The run.alive payload. Runs on the heartbeat thread, so it copies
        the running set before reading it."""
        ids = list(self._running)
        return {"running": ids[:ALIVE_MAX_IDS], "n_running": len(ids)}

    def _run_id(self, runner):
        for t in getattr(runner, "_dep_map", {}) or {}:
            ctxt = getattr(t, "ctxt", None)
            rid = getattr(ctxt, "run_id", None)
            if rid:
                return rid
        return os.environ.get("DFM_RUN_ID")

    def _id(self, node) -> str:
        nid = self._ids.get(id(node))
        if nid is None:
            name = str(getattr(node, "name", None) or "<anon>")
            n = self._names.get(name, 0) + 1
            self._names[name] = n
            nid = name if n == 1 else "%s#%d" % (name, n)
            self._ids[id(node)] = nid
            self._keep.append(node)
        return nid

    def _nodes(self, dep_map) -> List[Dict[str, Any]]:
        from .task_node_compound import TaskNodeCompound
        out = []
        for node in dep_map:
            if id(node) in self._sent:
                continue
            self._sent.add(id(node))
            nid = self._id(node)
            rec = {
                "id": nid,
                "name": node.name,
                "kind": "compound" if isinstance(node, TaskNodeCompound) else "leaf",
                "parent": self._id(node.parent) if getattr(node, "parent", None) is not None else None,
                "needs": [{"id": self._id(d), "block": bool(b)}
                          for d, b in (getattr(node, "needs", None) or [])],
            }
            label = _display_name(node)
            if label and label != node.name:
                rec["label"] = label
            rd = getattr(node, "rundir", None)
            if rd is not None:
                rec["rundir"] = rd if isinstance(rd, str) else "/".join(str(x) for x in rd)
            out.append(rec)
        return out

    def _done(self, node):
        nid = self._id(node)
        self._running.pop(nid, None)
        res = getattr(node, "result", None)
        p = {"id": nid, "state": "done"}
        if res is not None:
            p["status"] = res.status
            p["changed"] = bool(res.changed)
            if getattr(res, "cache_hit", False):
                p["cache_hit"] = True
            if getattr(res, "base_hit", False):
                p["base_hit"] = True
        start, end = getattr(node, "start", None), getattr(node, "end", None)
        if start is not None and end is not None:
            p["dur"] = round((end - start).total_seconds(), 3)
        rd = getattr(node, "rundir", None)
        if isinstance(rd, str):
            p["rundir"] = rd
            log = _log_path(node, rd)
            if log is not None:
                p["log"] = log
        if res is None:
            key = "unknown"
        elif res.status != 0:
            key = "failed"
        elif getattr(res, "cache_hit", False):
            key = "cache_hit"
        elif getattr(res, "base_hit", False):
            key = "base_hit"
        elif not res.changed:
            key = "uptodate"
        else:
            key = "ok"
        self._counts[key] = self._counts.get(key, 0) + 1
        # Markers the task returned rather than added live
        for m in (getattr(res, "markers", None) or []):
            self._marker(node, m)
        self.emitter.emit("task.state", **p)

    def _marker(self, node, m):
        if m is None:
            return
        nid = self._id(node)
        sent = self._markers.setdefault(nid, set())
        if id(m) in sent:
            return
        sent.add(id(m))
        self._keep.append(m)
        sev = getattr(m, "severity", None)
        p = {"id": nid,
             "severity": getattr(sev, "value", sev),
             "msg": _trunc(str(getattr(m, "msg", "")), MSG_MAX)}
        loc = getattr(m, "loc", None)
        if loc is not None:
            p["loc"] = {"path": loc.path, "line": loc.line, "pos": loc.pos}
        self.emitter.emit("task.marker", **p)

    def _exec(self, node, info):
        info = info or {}
        p = {"id": self._id(node), "phase": info.get("phase"),
             "cmd": _trunc_cmd(info.get("cmd") or []),
             "logfile": info.get("logfile")}
        if info.get("phase") == "end":
            p["rc"] = info.get("rc")
        self.emitter.emit("task.exec", **p)


def _display_name(node):
    try:
        return node._get_display_name()
    except Exception:
        return None


def _log_path(node, rundir):
    try:
        path = os.path.join(rundir, node._get_log_filename())
    except Exception:
        return None
    return path if os.path.isfile(path) else None


def _trunc(s, n):
    return s if len(s) <= n else s[:n] + "..."


def _trunc_cmd(cmd):
    out = []
    used = 0
    for a in list(cmd)[:CMD_MAX_ARGS]:
        a = str(a)
        if used + len(a) > CMD_MAX_CHARS:
            out.append(_trunc(a, max(0, CMD_MAX_CHARS - used)))
            break
        out.append(a)
        used += len(a)
    return out
