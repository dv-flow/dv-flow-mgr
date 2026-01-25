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
    json : bool = False
    verbose : bool = False
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

    def enter(self):
        pass

    def leave(self):
        pass

    def marker(self, marker):
        """Receives markers during loading"""
        self.show_marker(marker)
        self.has_severity[marker.severity] += 1
        pass

    def event(self, task : 'Task', reason : 'Reason'):
        if reason == 'enter':
            self.level += 1
            # In verbose mode, show immediately; in non-verbose mode, defer until we know if it runs
            if self.verbose and not self.quiet:
                self.console.print("[green]>> [%d][/green] Task %s" % (self.level, task.name))
        elif reason == 'uptodate':
            # Task is up-to-date - in non-verbose mode, don't show it
            # In verbose mode, it was already shown in 'enter'
            pass
        elif reason == 'cache_hit':
            # Task is a cache hit - in non-verbose mode, don't show it
            # In verbose mode, it was already shown in 'enter'
            pass
        elif reason == 'run':
            # Task will actually run - show it now in non-verbose mode
            if not self.verbose and not self.quiet:
                self.console.print("[green]>> [%d][/green] Task %s" % (self.level, task.name))
        elif reason == 'leave':
            # Check if task was up-to-date (not changed) or cache hit
            is_uptodate = not task.result.changed if task.result else False
            is_cache_hit = task.result.cache_hit if (task.result and hasattr(task.result, 'cache_hit')) else False
            
            # Skip display of up-to-date/cache-hit tasks unless verbose mode
            if (is_uptodate or is_cache_hit) and not self.verbose and not self.quiet:
                self.level -= 1
                return
            
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
                    # Determine status suffix
                    status_suffix = ""
                    if is_cache_hit:
                        status_suffix = " (cache)"
                    elif is_uptodate:
                        status_suffix = " (up-to-date)"
                    
                    self.console.print("[green]<< [%d][/green] Task %s%s%s" % (
                        self.level, 
                        task.name,
                        status_suffix,
                        (delta_s if delta_s is not None else "")))
                else:
                    self.console.print("[red]<< [%d][/red] Task %s" % (self.level, task.name))
            self.level -= 1
        elif reason in ("start", "end"):
            pass
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

