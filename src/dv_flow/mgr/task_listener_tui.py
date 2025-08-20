#****************************************************************************
#* task_listener_tui.py
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
from datetime import datetime
from rich.console import Console
from rich.live import Live
from rich.table import Table
from typing import Any, ClassVar, Dict, List
from .task_data import SeverityE

@dc.dataclass
class TaskListenerTui(object):
    console : Console = dc.field(default=None)
    level : int = 0
    quiet : bool = False
    json : bool = False
    has_severity : Dict[SeverityE, int] = dc.field(default_factory=dict)
    _table : Any = None
    _live  : Any = None
    _tasks : List = dc.field(default_factory=list)

    sev_pref_m : ClassVar = {
        "info": "[blue]I[/blue]",
        SeverityE.Info: "[blue]I[/blue]",
        "warn": "[yellow]W[/yellow]",
        SeverityE.Warning: "[yellow]W[/yellow]",
        "error": "[red]E[/red]",
        SeverityE.Error: "[red]E[/red]",
    }

    def __post_init__(self):
        self.console = Console(highlight=False)
        for sev in SeverityE:
            self.has_severity[sev] = 0

    def enter(self):
        self._table = Live(self._create())
        self._live = self._table.__enter__()

    def leave(self):
        self._table.__exit__(None, None, None)

    def _create(self):
        table = Table()
        table.add_column("Task")
        table.add_column("Status")

        idx = 0
        while idx < len(self._tasks):
            row = self._tasks[idx]
            table.add_row(row[0], row[1])
            if "Success" in row[1] or "Fail" in row[1]:
                self._tasks.pop(idx)
            else:
                idx += 1
        return table

    def marker(self, marker):
        """Receives markers during loading"""
        self.show_marker(marker)
        self.has_severity[marker.severity] += 1
        pass

    def event(self, task : 'Task', reason : 'Reason'):
        if reason == 'enter':
            self.level += 1
            self._tasks.append((task.name, "[green]Running"))
        elif reason == 'leave':
            if self.quiet:
                if task.result.changed:
                    self.console.print("[green]Done:[/green] %s" % (task.name,))
            else:
                delta_s = None
                if task.start is not None and task.end is not None:
                    delta = task.end - task.start
                    if delta.total_seconds() > 1:
                        delta_s = " %0.2fs" % delta.total_seconds()
                    else:
                        delta_s = " %0.2fmS" % (1000*delta.total_seconds())

                for m in task.result.markers:
                    self.show_marker(m, task.name, task.rundir)

                idx = -1
                for i,t in enumerate(self._tasks):
                    if t[0] == task.name:
                        idx = i
                        break

                if task.result.status == 0:
                    self._tasks[idx] = (task.name, "[green]Success")
                else:
                    self._tasks[idx] = (task.name, "[red]Fail")

            self._live.update(self._create())
            self.level -= 1
        elif reason == "start":
            self.enter()
        elif reason == "end":
            self.leave()
        else:
            self.console.print("[red]-[/red] Task %s" % task.name)
        pass

    def show_marker(self, m, name=None, rundir=None):
        severity_s = str(m.severity)

        if m.severity in self.sev_pref_m.keys():
            sev_pref = self.sev_pref_m[m.severity]
        elif severity_s in self.sev_pref_m.keys():
            sev_pref = self.sev_pref_m[severity_s]
        else:
            sev_pref = ""

        # Escape anything that looks like a styling marker
        marker_m = m.msg.replace("[", "\\[")

        msg = "  %s%s: %s" % (
            sev_pref,
            (" " + name) if name is not None and name != "" else "",
            marker_m)
        


        if m.loc is not None:

            try:
                self.console.print("%s" % msg)
            except Exception as e:
                self._log.error("Problem displaying message \"%s\" to the console: %s" % (msg, e))
            if m.loc.line != -1 and m.loc.pos != -1:
                self.console.print("    %s:%d:%d" % (m.loc.path, m.loc.line, m.loc.pos))
            elif m.loc.line != -1:
                self.console.print("    %s:%d" % (m.loc.path, m.loc.line))
            else:
                self.console.print("    %s" % m.loc.path)
        else:
            try:
                self.console.print("%s%s" % (
                    msg, 
                    ("(%s)" % rundir) if rundir is not None else ""))
            except Exception as e:
                self._log.error("Problem displaying message \"%s\" to the console: %s" % (msg, e))

        pass

