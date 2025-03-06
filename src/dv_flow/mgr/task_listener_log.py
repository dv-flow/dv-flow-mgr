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
            for m in task.result.markers:
                print("  %s" % m)
            if self.quiet:
                if task.result.changed:
                    self.console.print("[green]Done:[/green] %s" % (task.name,))
            else:
                self.console.print("[green]<[%d][/green] Task %s" % (self.level, task.name))
            self.level -= 1
        else:
            self.console.print("[red]-[/red] Task %s" % task.name)
        pass

