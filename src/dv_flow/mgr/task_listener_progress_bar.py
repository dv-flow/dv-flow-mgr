#****************************************************************************
#* task_listener_progress_bar.py
#*
#* Simple progress bar task listener
#*
#* Displays only a single progress bar that increments as tasks complete.
#* No task details, markers, or status information are shown.
#****************************************************************************
import dataclasses as dc
from typing import ClassVar, Dict, Optional
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.live import Live
from .task_data import SeverityE
from .task_node import TaskNode


@dc.dataclass
class TaskListenerProgressBar(object):
    console: Optional[Console] = dc.field(default=None)
    quiet: bool = False
    json: bool = False
    verbose: bool = False
    has_severity: Dict[SeverityE, int] = dc.field(default_factory=dict)
    message: str = dc.field(default="Running tasks...")

    # Internal state
    _progress: Optional[Progress] = None
    _live: Optional[Live] = None
    _progress_task_id: Optional[int] = None
    _running: bool = False
    
    # Statistics tracking
    _total_tasks: int = 0
    _completed_tasks: int = 0

    def __post_init__(self):
        self.console = Console(highlight=False)
        for sev in SeverityE:
            self.has_severity[sev] = 0

    def enter(self):
        if self._running:
            return
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console
        )
        self._progress_task_id = self._progress.add_task(
            self.message, 
            total=self._total_tasks if self._total_tasks > 0 else 100,
            completed=0
        )
        self._live = Live(self._progress, console=self.console, refresh_per_second=10)
        self._live.__enter__()
        self._running = True

    def leave(self):
        if self._live is not None:
            self._live.stop()
            self._live.__exit__(None, None, None)
            self._live = None
        self._running = False

    def event(self, task: TaskNode, reason: str):
        if reason == 'start':
            # task is actually the runner when reason is 'start'
            # Check if runner has total task count
            if hasattr(task, 'total_task_count'):
                self._total_tasks = task.total_task_count
            self.enter()
            return
        if reason == 'end':
            self.leave()
            return
        if not self._running:
            self.enter()
        if reason == 'enter':
            # Don't increment total - we already know it from the start event
            # Update progress total if needed (for dynamic tasks)
            if self._total_tasks == 0:
                self._total_tasks = 1
            if self._progress is not None and self._progress_task_id is not None:
                self._progress.update(self._progress_task_id, total=self._total_tasks)
        elif reason == 'leave':
            # Task completed - increment progress
            self._completed_tasks += 1
            if self._progress is not None and self._progress_task_id is not None:
                self._progress.update(self._progress_task_id, completed=self._completed_tasks)

    def marker(self, marker):
        # Only used during loading phase - track severity but don't display
        self.has_severity[marker.severity] += 1
