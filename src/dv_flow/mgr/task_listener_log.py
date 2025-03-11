import dataclasses as dc
from datetime import datetime
from rich.console import Console

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
                    "warn": "[yellow]W[/yellow]",
                    "error": "[red]E[/red]",
                }
                for m in task.result.markers:
                    msg = "  %s %s: %s" % (
                        sev_pref_m[m.severity], 
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

