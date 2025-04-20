#****************************************************************************
#* task_listener_log.py
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
from typing import ClassVar, Dict
from .task_data import SeverityE

@dc.dataclass
class TaskListenerLog(object):
    console : Console = dc.field(default=None)
    level : int = 0
    quiet : bool = False
    has_severity : Dict[SeverityE, int] = dc.field(default_factory=dict)

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

    def marker(self, marker):
        """Receives markers during loading"""
        self.show_marker(marker)
        self.has_severity[marker.severity] += 1
        pass

    def event(self, task : 'Task', reason : 'Reason'):
        if reason == 'enter':
            self.level += 1
            if not self.quiet:
                self.console.print("[green]>> [%d][/green] Task %s" % (self.level, task.name))
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

                if task.result.status == 0:
                    self.console.print("[green]<< [%d][/green] Task %s%s%s" % (
                        self.level, 
                        task.name,
                        ("" if task.result.changed else " (up-to-date)"),
                        (delta_s if delta_s is not None else "")))
                else:
                    self.console.print("[red]<< [%d][/red] Task %s" % (self.level, task.name))
            self.level -= 1
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

        msg = "  %s%s: %s" % (
            sev_pref,
            (" " + name) if name is not None and name != "" else "",
            m.msg)

        if m.loc is not None:
            self.console.print("%s" % msg)
            if m.loc.line != -1 and m.loc.pos != -1:
                self.console.print("    %s:%d:%d" % (m.loc.path, m.loc.line, m.loc.pos))
            elif m.loc.line != -1:
                self.console.print("    %s:%d" % (m.loc.path, m.loc.line))
            else:
                self.console.print("    %s" % m.loc.path)
        else:
            self.console.print("%s%s" % (
                msg, 
                ("(%s)" % rundir) if rundir is not None else ""))

        pass

