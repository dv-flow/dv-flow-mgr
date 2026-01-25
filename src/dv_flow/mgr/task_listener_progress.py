#****************************************************************************
#* task_listener_progress.py
#*
#* Rich-based task progress listener
#*
#* Displays a live list of tasks with a spinner while running
#* and a final status code when complete:
#*   D - done (success, no errors or warnings)
#*   U - up-to-date (task was skipped because it was already current)
#*   C - cache hit (task result restored from cache)
#*   W - completed with warnings (no errors)
#*   E - completed with errors
#*
#* When not in verbose mode, up-to-date and cache hit tasks are hidden
#* and only tasks that are actually evaluated are displayed.
#*
#* Any markers produced by the task are displayed indented
#* directly below the task entry when the task completes.
#* The final table remains visible after execution completes and includes
#* summary statistics (total tasks, up-to-date, cache hits/misses, etc.).
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
    verbose : bool = False
    has_severity : Dict[SeverityE, int] = dc.field(default_factory=dict)

    # Internal state
    _progress : Optional[Progress] = None
    _live : Optional[Live] = None
    _task_row_map : Dict[Any, Dict[str, Any]] = dc.field(default_factory=dict)  # task -> info
    _order : list = dc.field(default_factory=list)  # maintain insertion/display order
    _running : bool = False
    
    # Statistics tracking
    _total_tasks : int = 0
    _uptodate_count : int = 0
    _cache_hit_count : int = 0
    _done_count : int = 0
    _error_count : int = 0
    _warning_count : int = 0
    _cache_enabled : bool = False

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
        self._live = Live(self._render_group(), console=self.console, refresh_per_second=20)
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
            # task is actually the runner when reason is 'start'
            if hasattr(task, 'cache_providers'):
                self._cache_enabled = bool(task.cache_providers)
            self.enter()
            return
        if reason == 'end':
            self.leave()
            return
        if not self._running:
            self.enter()
        if reason == 'enter':
            self._total_tasks += 1
            # In verbose mode, add task row immediately with spinner
            # In non-verbose mode, defer until we know if it will run
            if self.verbose:
                if task not in self._task_row_map and self._progress is not None:
                    tid = self._progress.add_task(
                        "", total=1, completed=0,
                        status="[cyan]…", name=task.name, elapsed=""
                    )
                    self._task_row_map[task] = { 'progress_id': tid, 'markers': [], 'elapsed': '', 'cache_hit': False }
                    self._order.append(task)
                    # Trigger a manual refresh
                    if self._live:
                        self._live.update(self._render_group())
        elif reason == 'uptodate':
            # Task is up-to-date - in non-verbose mode, don't show it at all
            # In verbose mode, task was already added in 'enter', will show 'U' on leave
            self._uptodate_count += 1
        elif reason == 'cache_hit':
            # Track cache hits (even if not displayed)
            self._cache_hit_count += 1
            # Mark in task_row_map if it exists (verbose mode)
            if task in self._task_row_map:
                self._task_row_map[task]['cache_hit'] = True
        elif reason == 'run':
            # Task will actually run - add to display if not already added
            if task not in self._task_row_map and self._progress is not None:
                tid = self._progress.add_task(
                    "", total=1, completed=0,
                    status="[cyan]…", name=task.name, elapsed=""
                )
                self._task_row_map[task] = { 'progress_id': tid, 'markers': [], 'elapsed': '', 'cache_hit': False }
                self._order.append(task)
                # Trigger a manual refresh
                if self._live:
                    self._live.update(self._render_group())
        elif reason == 'leave':
            info = self._task_row_map.get(task)
            if info is None:
                # Task wasn't displayed (up-to-date in non-verbose mode)
                return
            
            # Check if task was up-to-date (not changed) or cache hit
            is_uptodate = not task.result.changed if task.result else False
            is_cache_hit = info.get('cache_hit', False)
            
            # Determine status code
            err_ct = sum(1 for m in task.result.markers if m.severity == SeverityE.Error)
            warn_ct = sum(1 for m in task.result.markers if m.severity == SeverityE.Warning)
            if task.result.status != 0 or err_ct > 0:
                status_code = '[red]E[/red]'
                self._error_count += 1
            elif warn_ct > 0:
                status_code = '[yellow]W[/yellow]'
                self._warning_count += 1
            elif is_cache_hit:
                status_code = '[magenta]C[/magenta]'  # C for cache hit
            elif is_uptodate:
                status_code = '[blue]U[/blue]'
            else:
                status_code = '[green]D[/green]'
                self._done_count += 1
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
        return Group(self._progress if self._running else self._final_panel())

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
        
        # Build summary statistics
        summary_parts = [f"Total: {self._total_tasks}"]
        if self._uptodate_count > 0:
            summary_parts.append(f"Up-to-date: {self._uptodate_count}")
        if self._cache_enabled:
            cache_miss = self._done_count + self._error_count + self._warning_count
            summary_parts.append(f"Cache: {self._cache_hit_count} hit / {cache_miss} miss")
        if self._done_count > 0:
            summary_parts.append(f"Done: {self._done_count}")
        if self._error_count > 0:
            summary_parts.append(f"[red]Errors: {self._error_count}[/red]")
        if self._warning_count > 0:
            summary_parts.append(f"[yellow]Warnings: {self._warning_count}[/yellow]")
        
        summary = " | ".join(summary_parts)
        title = f"Task Summary ({summary})"
        
        return Panel(table, title=title, border_style="blue")

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
