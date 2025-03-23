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
from .task_data import SeverityE

@dc.dataclass
class TaskListenerLog(object):
    console : Console = dc.field(default=None)
    level : int = 0
    quiet : bool = False

    def __post_init__(self):
        self.console = Console(highlight=False)

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

                sev_pref_m = {
                    "info": "[blue]I[/blue]",
                    SeverityE.Info: "[blue]I[/blue]",
                    "warn": "[yellow]W[/yellow]",
                    SeverityE.Warning: "[yellow]W[/yellow]",
                    "error": "[red]E[/red]",
                    SeverityE.Error: "[red]E[/red]",
                }
                for m in task.result.markers:
                    severity_s = str(m.severity)

                    if m.severity in sev_pref_m.keys():
                        sev_pref = sev_pref_m[m.severity]
                    elif severity_s in sev_pref_m.keys():
                        sev_pref = sev_pref_m[severity_s]
                    else:
                        sev_pref = ""

                    msg = "  %s %s: %s" % (
                        sev_pref,
                        task.name,
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
                        self.console.print("%s (%s)" % (msg, task.rundir))
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

