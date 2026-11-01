#****************************************************************************
#* recorder.py -- the end-of-run results recorder
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
"""Write ``rundir/out/<run-id>/results.json`` at the end of a run.

1. Pick the root Result from each root task's output (an ``is_a(std.Result)``
   item), wrapping several, or synthesize a ``std.TaskResult`` from the task.
2. Attach every failed task in the roots' subgraph that no Result accounts for
   as a ``std.TaskResult`` under the root's ``_tasks`` node, and raise a
   passing root to ``error`` when there is one, so the record agrees with the
   run's exit status.
3. Stamp artifacts with mtime/size and mark nodes from up-to-date or
   cache-hit tasks ``reused``.
4. Compute the summary, write ``results.json`` (atomically) and
   ``summary.md``, and point ``out/latest`` at the run.

The recorder is a detail listener on the runner (``event``), which is how it
learns which tasks were skipped, up to date or cache hits. Writing results
never changes the run's verdict; the caller wraps ``record`` accordingly.
"""
import datetime
import json
import logging
import os
import socket
import time
from typing import Any, Callable, Dict, List, Optional

from .convert import as_dict, convert_diagnostic, to_dict, MAX_DIAGS
from .lineage import RESULT_TYPE, is_result_type, type_lineage
from .model import ResultNode, ResultsFile, RunInfo
from .roles import role_of
from .rollup import TASKS_GROUP
from .status import worst, worst_of
from .summary import compute_summary

_log = logging.getLogger("ResultsRecorder")

RESULTS_FILE = "results.json"
SUMMARY_FILE = "summary.md"


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.astimezone().isoformat(timespec="seconds")
    except Exception:
        return str(dt)


def _leaf(name: str) -> str:
    return name.rsplit(".", 1)[-1] if name else name


class ResultsRecorder(object):

    def __init__(self, runner, roots, rundir: str, run_id: str,
                 argv: Optional[List[str]] = None, start_time: Optional[float] = None,
                 resolve: Optional[Callable] = None, max_diags: int = MAX_DIAGS,
                 config=None):
        self.runner = runner
        self.roots = list(roots) if isinstance(roots, (list, tuple)) else [roots]
        self.rundir = os.path.abspath(rundir)
        self.run_id = run_id
        self.argv = list(argv) if argv is not None else []
        self.start_time = start_time if start_time is not None else time.time()
        self.end_time = None
        self.max_diags = max_diags
        if config is None:
            from .config import ResultsConfig
            config = ResultsConfig()
        self.config = config
        self.written: List[str] = []
        self.warnings: List[str] = []
        if resolve is None:
            builder = getattr(runner, "builder", None)
            loader = getattr(builder, "loader", None) if builder is not None else None
            if loader is not None and hasattr(loader, "findType"):
                resolve = loader.findType
        self.resolve = resolve
        self._skipped = set()
        self._reused = set()

    @property
    def out_dir(self) -> str:
        return os.path.join(self.rundir, "out", self.run_id)

    @property
    def path(self) -> str:
        return os.path.join(self.out_dir, RESULTS_FILE)

    # -- runner listener ---------------------------------------------------

    def event(self, subject, reason, info=None):
        name = getattr(subject, "name", None)
        if name is None:
            return
        if reason == "skipped":
            self._skipped.add(name)
        elif reason in ("uptodate", "cache_hit"):
            self._reused.add(name)

    # -- graph facts -------------------------------------------------------

    def _nodes(self):
        from ..summary_builtin import ordered_nodes
        return ordered_nodes(self.roots)

    def _status(self, node) -> Optional[int]:
        r = getattr(node, "result", None)
        if r is not None:
            return r.status
        from ..summary_builtin import _load_disk_result
        d = _load_disk_result(node)
        return d.get("status") if d is not None else None

    def _is_skipped(self, node) -> bool:
        if node.name in self._skipped:
            return True
        try:
            from ..task_runner import TaskState
            return getattr(self.runner, "_task_state", {}).get(node) == TaskState.SKIPPED
        except Exception:
            return False

    def _is_reused(self, node) -> bool:
        if node.name in self._reused:
            return True
        r = getattr(node, "result", None)
        return bool(r is not None and (getattr(r, "cache_hit", False)
                                       or getattr(r, "base_hit", False)))

    def _rundir(self, node) -> Optional[str]:
        from ..summary_builtin import node_rundir
        return node_rundir(node, self.rundir)

    # -- step 1: the root Result -------------------------------------------

    def _convert(self, item) -> Dict[str, Any]:
        return to_dict(item, self.resolve, self.max_diags, self.warnings)

    def _root_items(self, node):
        from .collect import top_results
        out = getattr(node, "output", None)
        return top_results(getattr(out, "output", None) or [], self.resolve)

    def _times(self, node, d):
        st, en = getattr(node, "start", None), getattr(node, "end", None)
        if st is not None:
            d.setdefault("start_time", _iso(st))
        if en is not None:
            d.setdefault("end_time", _iso(en))

    def synthesize(self, node) -> Dict[str, Any]:
        """A ``std.TaskResult`` for a task that produced no Result."""
        status = self._status(node)
        skipped = self._is_skipped(node)
        r = getattr(node, "result", None)
        markers = list(getattr(r, "markers", None) or []) if r is not None else []
        if r is None:
            from ..summary_builtin import _load_disk_result
            dd = _load_disk_result(node)
            if dd is not None:
                markers = dd.get("markers", [])
        diags = [convert_diagnostic(m) for m in markers]
        for dg in diags:
            dg.setdefault("category", "tool")

        if skipped:
            blocker = self._blocker(node)
            st = "notrun"
            msg = ("blocked: %s failed" % blocker.name) if blocker is not None \
                else "not run: a task it depends on failed"
        elif status is None:
            st, msg = "notrun", "not run"
        elif status == 0:
            st, msg = "pass", ""
        else:
            st = "error"
            first = next((dg["msg"] for dg in diags if dg["severity"] in ("error", "fatal")), None)
            msg = first or "exit status %d" % status

        rundir = self._rundir(node)
        arts = []
        out = getattr(node, "output", None)
        for it in (getattr(out, "output", None) or []):
            d = as_dict(it)
            if d.get("src") not in (None, "", node.name):
                continue        # passed through from a need, not this task's
            if d.get("type") and (d["type"] == "std.FileSet" or
                                  "std.FileSet" in type_lineage(d["type"], self.resolve)):
                d = dict(d)
                role = role_of(d)
                attrs = [a for a in (d.get("attributes") or []) if not str(a).startswith("role=")]
                d["attributes"] = ["role=%s" % role] + attrs
                arts.append(d)
        if rundir:
            try:
                logname = node._get_log_filename()
            except Exception:
                logname = None
            if logname and os.path.isfile(os.path.join(rundir, logname)):
                arts.insert(0, {"type": "std.FileSet", "filetype": "taskLog",
                                "basedir": rundir, "files": [logname],
                                "attributes": ["role=log"]})

        d = {"type": "std.TaskResult", "name": _leaf(node.name), "status": st,
             "msg": msg, "task": node.name, "diagnostics": diags, "artifacts": arts}
        if rundir:
            d["rundir"] = rundir
        self._times(node, d)
        ret = self._convert(d)
        return ret

    def _blocker(self, node):
        """The first failed (not merely skipped) task this node depends on,
        breadth first through its needs."""
        from collections import deque
        seen = set()
        q = deque(n for n, _ in getattr(node, "needs", []) or [])
        while q:
            n = q.popleft()
            if id(n) in seen:
                continue
            seen.add(id(n))
            st = self._status(n)
            if st not in (None, 0) and not self._is_skipped(n):
                return n
            q.extend(m for m, _ in getattr(n, "needs", []) or [])
            q.extend(t for t in getattr(n, "tasks", []) or [] if t is not n)
        return None

    def _root_result(self, node) -> Dict[str, Any]:
        # A skipped task passes its needs' items through; Results among them
        # are its inputs, not its verdict.
        items = [] if self._is_skipped(node) else self._root_items(node)
        if len(items) == 1:
            d = self._convert(items[0])
        elif len(items) > 1:
            kids = [self._convert(it) for it in items]
            d = self._convert({"type": RESULT_TYPE, "name": _leaf(node.name),
                               "task": node.name, "children": kids})
            d["children"] = kids
        else:
            return self.synthesize(node)
        if not d.get("name"):
            d["name"] = _leaf(node.name)
        if not d.get("task"):
            d["task"] = node.name
        if not d.get("rundir"):
            rd = self._rundir(node)
            if rd:
                d["rundir"] = rd
        self._times(node, d)
        return d

    # -- selected tests that reported nothing (std.TestRunner) ---------------

    def _plan_result(self, node, root_d, synthesized):
        """Complete the root's Result from its runner's selection: every
        selected test that reported no Result becomes a `notrun` TestResult
        (blocked by a failed task it depends on) or an `error` one ("no
        result produced"), under its suite path. When the runner itself
        reported nothing (it was skipped because a build failed), the tree is
        built from the tests' own Results."""
        plan = getattr(node, "test_plan", None)
        if plan is None:
            return root_d
        try:
            runs = plan.runs(node)
        except Exception as e:
            _log.debug("test plan for %s unavailable: %s" % (node.name, e))
            return root_d
        if synthesized:
            root_d = self._convert({"type": "std.TestRunResult", "name": _leaf(node.name),
                                    "task": node.name, "status": "pass"})
            root_d["children"] = []
            rd = self._rundir(node)
            if rd:
                root_d["rundir"] = rd
            self._times(node, root_d)

        tasks = {n.get("task") for n in self._walk(root_d) if n.get("task")}

        def reported(run_nodes):
            for rn in run_nodes:
                for t in tasks:
                    if t == rn.name or t.startswith(rn.name + "."):
                        return True
            return False

        changed = False
        for path, run_nodes in runs:
            if run_nodes and reported(run_nodes):
                continue
            items = []
            if synthesized:
                for rn in run_nodes:
                    out = getattr(rn, "output", None)
                    from .collect import top_results
                    items.extend(top_results(getattr(out, "output", None) or [],
                                             self.resolve))
            if items:
                leaves = [self._convert(it) for it in items]
            else:
                leaves = [self._missing(path, run_nodes)]
            parent = self._suite_path(root_d, path[:-1])
            for lf in leaves:
                if not lf.get("name"):
                    lf["name"] = path[-1]
                parent.setdefault("children", []).append(lf)
                for t in self._walk(lf):
                    if t.get("task"):
                        tasks.add(t["task"])
            changed = True
        if changed:
            self._rollup_statuses(root_d, keep_own=not synthesized)
        return root_d

    def _missing(self, path, run_nodes):
        name = path[-1]
        task = run_nodes[0].name if run_nodes else ""
        blocker = None
        for rn in run_nodes:
            if self._is_skipped(rn) or self._status(rn) is None:
                blocker = self._blocker(rn)
            if blocker is not None:
                break
        if blocker is not None:
            st, msg = "notrun", "blocked: %s failed" % blocker.name
        elif not run_nodes:
            st, msg = "notrun", "not built"
        elif any(self._is_skipped(rn) for rn in run_nodes):
            st, msg = "notrun", "not run: a task it depends on failed"
        else:
            st, msg = "error", "no result produced"
        d = {"type": "std.TestResult", "name": name, "status": st, "msg": msg}
        if task:
            d["task"] = task
            rd = self._rundir(run_nodes[0])
            if rd:
                d["rundir"] = rd
        return self._convert(d)

    def _suite_path(self, root_d, segs):
        cur = root_d
        for seg in segs:
            nxt = None
            for c in cur.get("children") or []:
                if c.get("name") == seg:
                    nxt = c
                    break
            if nxt is None:
                nxt = self._convert({"type": "std.SuiteResult", "name": seg, "status": "pass"})
                nxt["children"] = []
                cur.setdefault("children", []).append(nxt)
            cur = nxt
        return cur

    def _rollup_statuses(self, d, keep_own=True):
        """Recompute parent statuses after adding entries: a parent is at
        least as bad as its worst child (its own verdict is kept)."""
        kids = d.get("children") or []
        for c in kids:
            self._rollup_statuses(c, keep_own)
        if not kids:
            return
        worst_kid = worst_of([c.get("status") for c in kids], "pass")
        st = worst(d.get("status") if keep_own else None, worst_kid)
        if st != d.get("status"):
            d["status"] = st
            d["passed"] = st == "pass"
            if d.get("type") in ("std.SuiteResult", "std.TestRunResult") or not keep_own:
                d.pop("msg", None)

    # -- step 2: unaccounted failures ---------------------------------------

    @staticmethod
    def _walk(d):
        yield d
        for c in d.get("children") or []:
            yield from ResultsRecorder._walk(c)

    def _ancestors(self, node):
        p = getattr(node, "parent", None)
        seen = set()
        while p is not None and id(p) not in seen:
            seen.add(id(p))
            yield p
            p = getattr(p, "parent", None)

    def unaccounted_failures(self, root_d) -> List[Any]:
        tasks = set()
        rundirs = []
        for n in self._walk(root_d):
            if n.get("task"):
                tasks.add(n["task"])
            if n.get("rundir"):
                rundirs.append(os.path.normpath(n["rundir"]))

        failed = []
        for node in self._nodes():
            if self._is_skipped(node):
                continue
            st = self._status(node)
            if st is None or st == 0:
                continue
            failed.append(node)

        # A compound that failed because something inside it failed is
        # reported through that task, not again on its own.
        inner = set()
        for n in failed:
            for a in self._ancestors(n):
                inner.add(id(a))
        failed = [n for n in failed if id(n) not in inner]

        def accounted(node):
            if node.name in tasks:
                return True
            if any(a.name in tasks for a in self._ancestors(node)):
                return True
            rd = self._rundir(node)
            if rd:
                rd = os.path.normpath(rd)
                for r in rundirs:
                    if r == rd or r.startswith(rd + os.sep):
                        return True
            return False

        return [n for n in failed if not accounted(n)]

    def attach_failures(self, root_d):
        extra = self.unaccounted_failures(root_d)
        if not extra:
            return root_d
        kids = [self.synthesize(n) for n in extra]
        # Unique names among the group
        seen = {}
        for k in kids:
            base = k["name"]
            if base in seen:
                seen[base] += 1
                k["name"] = "%s~%d" % (base, seen[base])
            else:
                seen[base] = 1
        group = {"type": RESULT_TYPE, "types": [RESULT_TYPE], "name": TASKS_GROUP,
                 "status": worst_of([k["status"] for k in kids], "pass"),
                 "msg": "%d task(s) failed outside any result" % len(kids),
                 "children": kids}
        group["passed"] = group["status"] == "pass"
        root_d.setdefault("children", []).append(group)
        own = root_d.get("status")
        new = worst(own, "error")
        if new != own:
            root_d["own_status"] = own
            root_d["status"] = new
            root_d["passed"] = False
            if own in ("pass", "skip") or not root_d.get("msg"):
                root_d["msg"] = "flow error: %d task(s) failed outside any result" % len(kids)
        return root_d

    # -- step 3: stamps and reuse --------------------------------------------

    def stamp(self, root_d):
        reused = {n.name for n in self._nodes() if self._is_reused(n)}
        for n in self._walk(root_d):
            if n.get("task") in reused:
                n["reused"] = True
            for a in n.get("artifacts") or []:
                stamps = []
                for f in a.get("files") or []:
                    p = f if os.path.isabs(f) else os.path.join(a.get("basedir") or "", f)
                    ent = {"path": p}
                    try:
                        st = os.stat(p)
                        ent["mtime"] = st.st_mtime
                        ent["size"] = st.st_size
                    except OSError:
                        pass
                    stamps.append(ent)
                a["stamps"] = stamps
        return root_d

    # -- the record ----------------------------------------------------------

    def _root_full(self, node):
        d = self._root_result(node)
        synthesized = (d.get("type") == "std.TaskResult" and d.get("task") == node.name)
        return self._plan_result(node, d, synthesized)

    def build(self) -> ResultsFile:
        if len(self.roots) == 1:
            root_d = self._root_full(self.roots[0])
        else:
            kids = [self._root_full(n) for n in self.roots]
            root_d = {"type": RESULT_TYPE, "types": [RESULT_TYPE], "name": "run",
                      "status": worst_of([k["status"] for k in kids], "pass"),
                      "children": kids}
            root_d["passed"] = root_d["status"] == "pass"
        self.attach_failures(root_d)
        self.stamp(root_d)
        root = ResultNode.model_validate(root_d)

        self.end_time = self.end_time or time.time()
        try:
            from ..__version__ import __version__ as ver
        except Exception:
            ver = ""
        run = RunInfo(
            id=self.run_id,
            root=self.roots[0].name if len(self.roots) == 1 else [n.name for n in self.roots],
            argv=self.argv, cwd=os.getcwd(), rundir=self.rundir,
            start_time=_iso(datetime.datetime.fromtimestamp(self.start_time)),
            end_time=_iso(datetime.datetime.fromtimestamp(self.end_time)),
            exit_status=int(getattr(self.runner, "status", 0) or 0),
            host=socket.gethostname(), dfm_version=str(ver))
        summary = compute_summary(root, walltime_s=self.end_time - self.start_time)
        return ResultsFile(run=run, summary=summary, result=root)

    def write(self, rf: ResultsFile) -> str:
        from ..run_id import set_latest
        os.makedirs(self.out_dir, exist_ok=True)
        tmp = self.path + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as fp:
            json.dump(rf.dump(), fp, indent=2)
            fp.write("\n")
        os.replace(tmp, self.path)
        self.written = [self.path]
        # summary.md always; junit/ctrf when configured
        for fmt in ["md"] + [f for f in self.config.formats if f != "md"]:
            self.write_format(rf, fmt)
        copies = {}
        if self.config.copy_logs:
            from .retention import copy_logs
            copies = copy_logs(rf, self.out_dir, self.rundir)
        if self.config.tree:
            try:
                from .tree import build_tree
                build_tree(rf, self.out_dir, copies)
            except Exception as e:
                _log.warning("could not build the results tree: %s" % e)
        set_latest(os.path.join(self.rundir, "out"), self.run_id)
        if self.config.keep_previous is not None:
            from .retention import prune
            prune(os.path.join(self.rundir, "out"), self.config.keep_previous,
                  self.run_id)
        return self.path

    def write_format(self, rf: ResultsFile, fmt: str) -> Optional[str]:
        """Write one rendering next to results.json. A failure is a warning."""
        from .config import FORMAT_FILES
        from .render import render
        path = os.path.join(self.out_dir, FORMAT_FILES[fmt])
        try:
            with open(path, "w") as fp:
                fp.write(render(rf, fmt))
            self.written.append(path)
            return path
        except Exception as e:
            _log.warning("could not write %s: %s" % (path, e))
            return None

    def record(self) -> Optional[ResultsFile]:
        rf = self.build()
        for w in self.warnings:
            _log.warning("results: %s" % w)
        self.write(rf)
        return rf
