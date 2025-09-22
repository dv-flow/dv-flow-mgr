#****************************************************************************
#* task_listener_progress.py
#*
#* Rich-based task progress listener
#*
#* Displays a live list of tasks with a spinner while running
#* and a final status code when complete:
#*   D - done (success, no errors or warnings)
#*   W - completed with warnings (no errors)
#*   E - completed with errors
#*
#* Any markers produced by the task are displayed indented
#* directly below the task entry when the task completes.
#* The final table remains visible after execution completes.
#****************************************************************************
import dataclasses as dc
from typing import ClassVar, Dict, Any, Optional
from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from .task_data import SeverityE

from .task_node import TaskNode

@dc.dataclass
class TaskListenerProgress(object):
    console : Optional[Console] = dc.field(default=None)
    quiet : bool = False
    json : bool = False
    has_severity : Dict[SeverityE, int] = dc.field(default_factory=dict)

    # Internal state
    _progress : Optional[Progress] = None
    _live : Optional[Live] = None
    _task_row_map : Dict[Any, Dict[str, Any]] = dc.field(default_factory=dict)  # task -> info
    _order : list = dc.field(default_factory=list)  # maintain insertion/display order
    _running : bool = False

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

    # Lifecycle hooks (start/end of overall run)
    def enter(self):
        if self._running:
            return
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("{task.fields[status]}"),
            TextColumn("{task.fields[name]}") ,
            TextColumn("{task.fields[elapsed]}")
        )
        self._live = Live(self._render_group(), console=self.console, refresh_per_second=10)
        self._live.__enter__()
        self._running = True

    def leave(self):
        # Freeze the final display: stop live refresh but leave content
        if self._live is not None:
            self._live.stop()
            # Re-render final static panel so it persists after stop
            self.console.print(self._final_panel())
            self._live.__exit__(None, None, None)
            self._live = None
        self._running = False

    # Event interface used by runner
    def event(self, task: TaskNode, reason: str):
        if reason == 'start':
            self.enter()
            return
        if reason == 'end':
            self.leave()
            return
        if not self._running:
            self.enter()
        if reason == 'enter':
            # Add task row
            if task not in self._task_row_map and self._progress is not None:
                # Create a task in Progress with a fixed total so we can mark complete to stop spinner
                tid = self._progress.add_task(
                    "", total=1, completed=0,
                    status="[cyan]…", name=task.name, elapsed=""
                )
                self._task_row_map[task] = { 'progress_id': tid, 'markers': [], 'elapsed': '' }
                self._order.append(task)
        elif reason == 'leave':
            info = self._task_row_map.get(task)
            if info is None:
                return
            # Determine status code
            err_ct = sum(1 for m in task.result.markers if m.severity == SeverityE.Error)
            warn_ct = sum(1 for m in task.result.markers if m.severity == SeverityE.Warning)
            if task.result.status != 0 or err_ct > 0:
                status_code = '[red]E[/red]'
            elif warn_ct > 0:
                status_code = '[yellow]W[/yellow]'
            else:
                status_code = '[green]D[/green]'
            # Compute elapsed time
            elapsed_s = ""
            if getattr(task, 'start', None) is not None and getattr(task, 'end', None) is not None:
                delta = task.end - task.start
                if delta.total_seconds() >= 1.0:
                    elapsed_s = f"{delta.total_seconds():0.2f}s"
                else:
                    elapsed_s = f"{delta.total_seconds()*1000:0.2f}ms"
                info['elapsed'] = elapsed_s
            if self._progress is not None:
                # Mark task complete to stop spinner and update elapsed
                self._progress.update(info['progress_id'], status=status_code, completed=1, elapsed=elapsed_s)
                self._progress.stop_task(info['progress_id'])
            # Collect markers for later rendering below
            if task.result.markers:
                info['markers'] = task.result.markers.copy()
            # Trigger a manual refresh
            if self._live:
                self._live.update(self._render_group())
        else:
            pass

    def marker(self, marker):
        # Only used during loading phase (before run). Mirror log behavior.
        self.show_marker(marker)
        self.has_severity[marker.severity] += 1

    # Rendering helpers
    def _render_group(self):
        # Build a table representation from current progress tasks
        table = Table.grid(padding=(0,1))
        table.add_column(justify="left")
        if self._progress is not None:
            for t in self._order:
                info = self._task_row_map[t]
                # Progress renders spinner+status+name; replicate status+name for static table until finished
                task_r = self._progress.tasks[ info['progress_id'] ]
                table.add_row(f"{task_r.fields['status']} {task_r.fields['name']}")
                # Add markers if available and task finished (status not spinner)
                if info.get('markers'):
                    for m in info['markers']:
                        table.add_row("  " + self._format_marker_line(m, t.name))
        return Group(self._progress if (self._live and self._live.is_started) else self._final_panel())

    def _final_panel(self):
        # Create a static panel summarizing all tasks with final statuses + markers
        table = Table.grid(padding=(0,1))
        table.add_column(justify="left")
        if self._progress is not None:
            for t in self._order:
                info = self._task_row_map[t]
                task_r = self._progress.tasks[ info['progress_id'] ]
                table.add_row(f"{task_r.fields['status']} {task_r.fields['name']}")
                if info.get('markers'):
                    for m in info['markers']:
                        table.add_row("  " + self._format_marker_line(m, t.name))
        return Panel(table, title="Task Summary", border_style="blue")

    # Marker formatting similar to log listener
    def show_marker(self, m, name=None, rundir=None):
        if self.console is not None:
            self.console.print(self._format_marker_line(m, name))

    def _format_marker_line(self, m, name=None):
        severity_s = str(m.severity)
        if m.severity in self.sev_pref_m:
            sev_pref = self.sev_pref_m[m.severity]
        elif severity_s in self.sev_pref_m:
            sev_pref = self.sev_pref_m[severity_s]
        else:
            sev_pref = ""
        marker_m = m.msg.replace("[", "\\[")
        msg = f"{sev_pref}{' ' + name if name else ''}: {marker_m}" if name else f"{sev_pref}: {marker_m}"
        if m.loc is not None:
            loc_parts = []
            if m.loc.line != -1:
                if m.loc.pos != -1:
                    loc_parts.append(f"{m.loc.path}:{m.loc.line}:{m.loc.pos}")
                else:
                    loc_parts.append(f"{m.loc.path}:{m.loc.line}")
            else:
                loc_parts.append(m.loc.path)
            msg += " (" + ", ".join(loc_parts) + ")"
        return msg
