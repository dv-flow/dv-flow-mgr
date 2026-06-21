#****************************************************************************
#* task_listener_report.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
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
#* Created on:
#*     Author:
#*
#****************************************************************************
import dataclasses as dc
import json
import logging
import os
import re
import shutil
from typing import ClassVar, List, Optional
from .task_data import SeverityE
from .task_node import TaskNode

# Format version for report.json -- bump when the schema changes incompatibly
REPORT_SCHEMA = "dvflow-report/1"

# Characters that are unsafe in a logs/<name>.log filename
_UNSAFE_NAME_CHARS = re.compile(r'[^A-Za-z0-9._-]+')


@dc.dataclass
class TaskListenerReport(object):
    """Task listener that aggregates per-task diagnostics into a publishable
    report bundle (logs, markers, status). Modeled on TaskListenerTrace: it
    accumulates task nodes via the runner's listener callback, then writes the
    bundle once the run has completed via generate().
    """

    # Root rundir, used to resolve any task.rundir that is still relative
    rundir: str = None
    # Name of the root task/package (for report metadata)
    root_name: str = ""

    _tasks: List[TaskNode] = dc.field(default_factory=list)
    _seen: set = dc.field(default_factory=set)

    _log: ClassVar = logging.getLogger("TaskListenerReport")

    def event(self, task: TaskNode, reason: str):
        """Runner listener callback. Accumulate each task once it completes.

        'leave' fires for every task -- including up-to-date and cache-hit
        tasks -- with task.result populated, so this captures the full tree.
        """
        if reason == "leave":
            key = id(task)
            if key not in self._seen:
                self._seen.add(key)
                self._tasks.append(task)

    def _resolve(self, task: TaskNode) -> str:
        """Resolve a task's absolute rundir path.

        After a task runs, the runner overwrites task.rundir with the
        fully-resolved absolute path (a string), so that is authoritative and
        used directly. The list-of-segments form (a node that never ran, or a
        synthetic node) is resolved against the root rundir.
        """
        rd = task.rundir
        if rd is None:
            return self.rundir
        if isinstance(rd, str):
            return rd if os.path.isabs(rd) else os.path.join(self.rundir, rd)

        # List of path segments; an absolute first segment is the base
        if len(rd) > 0 and os.path.isabs(rd[0]):
            path = rd[0]
            segs = rd[1:]
        else:
            path = self.rundir
            segs = rd
        for seg in segs:
            path = os.path.join(path, seg)
        return path

    def _load_exec_data(self, task: TaskNode, rundir: str) -> Optional[dict]:
        """Load the task's exec_data.json from its rundir, or None."""
        try:
            fname = task._get_exec_data_filename()
        except Exception:
            fname = "%s.exec_data.json" % task.name
        path = os.path.join(rundir, fname)
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, ValueError) as e:
                self._log.warning("Failed to read exec_data for %s: %s" % (task.name, e))
        return None

    def _task_facts(self, task: TaskNode, rundir: str):
        """Return (status, changed, cache_hit, marker_dicts, log_name) for a task.

        Prefers the on-disk exec_data.json (works for any backend) and falls
        back to the in-memory task.result when the file is unavailable.
        """
        result = task.result
        # cache_hit is a runtime property not persisted in exec_data; take it
        # from the in-memory result when present (cosmetic, defaults to False).
        cache_hit = bool(getattr(result, "cache_hit", False)) if result is not None else False

        data = self._load_exec_data(task, rundir)
        if data is not None:
            r = data.get("result", {})
            marker_dicts = [dict(m) for m in r.get("markers", [])]
            log_name = data.get("logfile")
            if log_name is None:
                log_name = self._inmem_log_name(task)
            return r.get("status"), r.get("changed"), cache_hit, marker_dicts, log_name

        # In-memory fallback
        if result is not None:
            marker_dicts = [
                m.model_dump(mode="json") if hasattr(m, "model_dump") else dict(m)
                for m in (result.markers or [])
            ]
            return result.status, result.changed, cache_hit, marker_dicts, self._inmem_log_name(task)

        return None, None, cache_hit, [], self._inmem_log_name(task)

    def _inmem_log_name(self, task: TaskNode) -> str:
        try:
            return task._get_log_filename()
        except Exception:
            return "%s.log" % task.name

    def generate(self, report_dir: str, generated_unix: Optional[int] = None) -> int:
        """Write the report bundle to report_dir.

        Returns the number of tasks with a non-zero status.
        """
        logs_dir = os.path.join(report_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        counts = {sev.value: 0 for sev in SeverityE}
        task_entries = []
        all_markers = []
        used_log_names = set()
        failed = 0

        for task in self._tasks:
            resolved_rundir = self._resolve(task)

            # Read task facts from the on-disk exec_data.json (backend-agnostic;
            # every backend writes it to the shared rundir), falling back to the
            # in-memory result when the file is absent.
            status, changed, cache_hit, marker_dicts, log_name = \
                self._task_facts(task, resolved_rundir)

            if status is not None and status != 0:
                failed += 1

            # Copy the logfile, if one exists
            log_rel = None
            src_log = os.path.join(resolved_rundir, log_name) if log_name else None
            if src_log is not None and os.path.isfile(src_log):
                dst_name = self._unique_log_name(task.name, used_log_names)
                used_log_names.add(dst_name)
                try:
                    shutil.copy2(src_log, os.path.join(logs_dir, dst_name))
                    log_rel = os.path.join("logs", dst_name)
                except OSError as e:
                    self._log.warning("Failed to copy log for %s: %s" % (task.name, e))

            # Tally markers
            for md in marker_dicts:
                sev = md.get("severity")
                if sev in counts:
                    counts[sev] += 1
                all_markers.append({"task": task.name, **md})

            task_entries.append({
                "name": task.name,
                "status": status,
                "changed": changed,
                "cache_hit": cache_hit,
                "rundir": resolved_rundir,
                "log": log_rel,
                "markers": marker_dicts,
            })

        report = {
            "schema": REPORT_SCHEMA,
            "root": self.root_name,
            "status": failed,
            "generated_unix": generated_unix,
            "counts": {
                "tasks_total": len(self._tasks),
                "tasks_failed": failed,
                "markers": counts,
            },
            "tasks": task_entries,
        }

        with open(os.path.join(report_dir, "report.json"), "w") as f:
            json.dump(report, f, indent=2)
            f.write("\n")

        with open(os.path.join(report_dir, "markers.jsonl"), "w") as f:
            for m in all_markers:
                f.write(json.dumps(m))
                f.write("\n")

        self._write_markdown(os.path.join(report_dir, "report.md"), report)

        return failed

    def _unique_log_name(self, task_name: str, used: set) -> str:
        """Sanitize a task name into a unique logs/<name>.log filename."""
        base = _UNSAFE_NAME_CHARS.sub("_", task_name).strip("_") or "task"
        name = "%s.log" % base
        if name not in used:
            return name
        idx = 1
        while True:
            name = "%s.%d.log" % (base, idx)
            if name not in used:
                return name
            idx += 1

    def _write_markdown(self, path: str, report: dict):
        """Write a human-readable summary suitable for a CI job summary."""
        counts = report["counts"]
        markers = counts["markers"]
        lines = []
        lines.append("# DV Flow Run Report")
        lines.append("")
        root = report.get("root") or "(unnamed)"
        overall = "PASS" if report["status"] == 0 else "FAIL"
        lines.append("- **Root:** `%s`" % root)
        lines.append("- **Result:** %s" % overall)
        lines.append("- **Tasks:** %d total, %d failed" % (
            counts["tasks_total"], counts["tasks_failed"]))
        lines.append("- **Markers:** %d error, %d warning, %d info" % (
            markers.get("error", 0), markers.get("warning", 0), markers.get("info", 0)))
        lines.append("")

        failed_tasks = [t for t in report["tasks"] if t["status"] not in (0, None)]
        if failed_tasks:
            lines.append("## Failed tasks")
            lines.append("")
            for t in failed_tasks:
                lines.append("### `%s` (status %s)" % (t["name"], t["status"]))
                if t.get("log"):
                    lines.append("")
                    lines.append("Log: `%s`" % t["log"])
                for m in t["markers"]:
                    lines.append("- **%s:** %s" % (
                        str(m.get("severity", "")).upper(), m.get("msg", "")))
                lines.append("")

        with open(path, "w") as f:
            f.write("\n".join(lines))
            f.write("\n")
