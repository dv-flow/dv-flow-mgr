import dataclasses as dc
from rich.console import Console

@dc.dataclass
class TaskListenerLog(object):
    console : Console = dc.field(default_factory=Console)
    level : int = 0
    quiet : bool = False

    def event(self, task : 'Task', reason : 'Reason'):
        if reason == 'enter':
            self.level += 1
            if not self.quiet:
                self.console.print("[green]>[%d][/green] Task %s" % (self.level, task.name))
        elif reason == 'leave':
            if self.quiet:
                if task.result.changed:
                    self.console.print("[green]Done:[/green] %s" % (task.name,))
            else:
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

                    self.console.print(msg)

                    if m.loc is not None:
                        if m.loc.line != -1 and m.loc.pos != -1:
                            self.console.print("    %s:%d:%d" % (m.loc.path, m.loc.line, m.loc.pos))
                        elif m.loc.line != -1:
                            self.console.print("    %s:%d" % (m.loc.path, m.loc.line))
                        else:
                            self.console.print("    %s" % m.loc.path)

                        pass
                if task.result.status == 0:
                    self.console.print("[green]<[%d][/green] Task %s" % (self.level, task.name))
                else:
                    self.console.print("[red]<[%d][/red] Task %s" % (self.level, task.name))
            self.level -= 1
        else:
            self.console.print("[red]-[/red] Task %s" % task.name)
        pass

