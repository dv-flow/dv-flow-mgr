#****************************************************************************
#* daemon_monitor.py
#*
#* Rich TUI monitor for the daemon, styled after Unix `top`.
#*
#* Layout:
#*   - Fixed status bar at the bottom: worker counts, pending tasks, uptime
#*   - Dynamic scrolling area above: running tasks, recent completions
#*
#* A single async loop uses wait_for with a timeout on the daemon socket
#* to multiplex between incoming events and periodic display refresh.
#* The layout renders immediately on attach.
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
#****************************************************************************
import asyncio
import json
import logging
import sys
import termios
import time
import tty
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from .daemon_events import (
    EVENT_WORKER_STATE,
    EVENT_TASK_DISPATCHED,
    EVENT_TASK_COMPLETED,
    EVENT_LOG,
    parse_event,
)


_log = logging.getLogger("DaemonMonitor")

# Maximum log/history lines to retain
MAX_LOG_LINES = 100
MAX_COMPLETED = 50

# Display refresh interval when no events arrive (seconds)
REFRESH_INTERVAL = 0.25

# ANSI escape sequences for alternate screen management
_ENTER_ALT_SCREEN = "\033[?1049h"
_LEAVE_ALT_SCREEN = "\033[?1049l"
_CURSOR_HOME = "\033[H"
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"


class DaemonMonitor:
    """Live TUI monitor for the daemon, modeled after Unix ``top``.

    The bottom of the screen shows a fixed status bar with aggregate
    stats (workers idle/busy, pending tasks, uptime).  The area above
    is a dynamic scrolling region showing running tasks and recent
    completions.

    Rendering uses explicit full-screen redraws via the alternate
    screen buffer to avoid differential-update artifacts when the
    content structure changes (tasks appearing / completing).
    """

    def __init__(self, console: Optional[Console] = None):
        self._console = console or Console()
        self._workers: List[Dict[str, Any]] = []
        self._active_tasks: List[Dict[str, Any]] = []
        self._completed_tasks: List[Dict[str, Any]] = []
        self._log_lines: List[str] = []
        self._start_time: float = time.monotonic()
        self._total_completed: int = 0

    # -- public read-only properties for tests --

    @property
    def workers(self) -> List[Dict[str, Any]]:
        return self._workers

    @property
    def active_tasks(self) -> List[Dict[str, Any]]:
        return self._active_tasks

    @property
    def completed_tasks(self) -> List[Dict[str, Any]]:
        return self._completed_tasks

    @property
    def log_lines(self) -> List[str]:
        return self._log_lines

    @property
    def total_completed(self) -> int:
        return self._total_completed

    # -- counts used by the status bar --

    def _worker_counts(self):
        total = len(self._workers)
        idle = sum(1 for w in self._workers if w.get("state") == "idle")
        busy = sum(1 for w in self._workers if w.get("state") == "busy")
        pending = total - idle - busy  # e.g. PEND in LSF
        return total, idle, busy, pending

    # -- event handling --

    def _handle_event(self, event: Dict[str, Any]):
        """Update internal state from a daemon event."""
        method = event.get("method", "")
        params = event.get("params", {})

        if method == EVENT_WORKER_STATE:
            self._update_worker(params)
        elif method == EVENT_TASK_DISPATCHED:
            params.setdefault("dispatched_at", time.monotonic())
            self._active_tasks.append(params)
        elif method == EVENT_TASK_COMPLETED:
            self._complete_task(params)
        elif method == EVENT_LOG:
            msg = params.get("msg", "")
            self._log_lines.append(msg)
            if len(self._log_lines) > MAX_LOG_LINES:
                self._log_lines = self._log_lines[-MAX_LOG_LINES:]
        # Unknown events silently ignored

    def _update_worker(self, params: Dict[str, Any]):
        wid = params.get("worker_id", "")
        for i, w in enumerate(self._workers):
            if w.get("worker_id") == wid:
                self._workers[i] = params
                return
        self._workers.append(params)

    def _complete_task(self, params: Dict[str, Any]):
        rid = params.get("request_id", "")
        removed = None
        new_active = []
        for t in self._active_tasks:
            if t.get("request_id") == rid and removed is None:
                removed = t
            else:
                new_active.append(t)
        self._active_tasks = new_active

        entry = dict(params)
        if removed:
            entry["name"] = removed.get("name", entry.get("name", ""))
        entry["completed_at"] = time.monotonic()
        self._completed_tasks.append(entry)
        if len(self._completed_tasks) > MAX_COMPLETED:
            self._completed_tasks = self._completed_tasks[-MAX_COMPLETED:]
        self._total_completed += 1

    # -- rendering --

    def _render(self) -> Layout:
        """Build the full-screen layout: dynamic area on top, status bar
        on bottom.

        The root Layout is given an explicit ``size`` equal to the
        terminal height so that every line is rendered and padded to
        the full terminal width, preventing ghost artifacts from
        previous frames.
        """
        height = self._console.height or 24
        layout = Layout(size=height)
        layout.split_column(
            Layout(name="main"),
            Layout(name="status", size=3),
        )
        layout["main"].update(self._render_main())
        layout["status"].update(self._render_status_bar())
        return layout

    def _render_main(self):
        """Dynamic area: running tasks table + recent completions."""
        run_table = Table(
            expand=True,
            show_lines=False,
            pad_edge=False,
            show_header=True,
            header_style="bold",
            title=None,
            border_style="dim",
        )
        run_table.add_column("PID", style="dim", width=8)
        run_table.add_column("WORKER", style="dim", width=10)
        run_table.add_column("TIME", justify="right", width=8)
        run_table.add_column("TASK", style="bold")

        now = time.monotonic()
        for t in self._active_tasks:
            worker_id = ""
            w_pid = ""
            task_name = t.get("name", t.get("request_id", ""))
            for w in self._workers:
                if w.get("current_task") == task_name or w.get("state") == "busy":
                    worker_id = w.get("worker_id", "")[:8]
                    w_pid = str(w.get("pid", ""))
                    break
            elapsed = now - t.get("dispatched_at", now)
            if elapsed >= 60:
                elapsed_str = "%d:%02d" % (int(elapsed) // 60, int(elapsed) % 60)
            else:
                elapsed_str = "%ds" % int(elapsed)
            run_table.add_row(w_pid, worker_id, elapsed_str, task_name)

        comp_table = Table(
            expand=True,
            show_lines=False,
            pad_edge=False,
            show_header=True,
            header_style="bold dim",
            title=None,
            border_style="dim",
        )
        comp_table.add_column("COMPLETED", ratio=3)
        comp_table.add_column("STATUS", justify="center", width=10)

        for t in self._completed_tasks[-10:]:
            status = t.get("status", 0)
            status_str = "[green]OK[/green]" if status == 0 else "[red]FAIL(%d)[/red]" % status
            comp_table.add_row(
                t.get("name", t.get("request_id", "")),
                status_str,
            )

        parts = []

        # Running section
        hdr = Text()
        hdr.append("RUNNING ", style="bold green")
        hdr.append("(%d)" % len(self._active_tasks))
        parts.append(hdr)
        if self._active_tasks:
            parts.append(run_table)
        else:
            parts.append(Text("  (idle)", style="dim"))
        parts.append(Text(""))

        # Completed section
        if self._completed_tasks:
            chdr = Text()
            chdr.append("COMPLETED ", style="bold")
            chdr.append("(%d)" % self._total_completed)
            parts.append(chdr)
            parts.append(comp_table)

        return Group(*parts)

    def _render_status_bar(self):
        """Fixed status bar at the bottom -- 3 lines."""
        total, idle, busy, pending_w = self._worker_counts()
        uptime_s = int(time.monotonic() - self._start_time)
        uptime_str = "%d:%02d:%02d" % (uptime_s // 3600, (uptime_s % 3600) // 60, uptime_s % 60)

        summary = Text()
        summary.append("dfm daemon", style="bold cyan")
        summary.append("  up %s" % uptime_str)
        summary.append("  |  workers: ", style="dim")
        summary.append("%d" % busy, style="green bold" if busy else "dim")
        summary.append(" busy", style="dim")
        summary.append(", %d" % idle, style="dim")
        summary.append(" idle", style="dim")
        if pending_w:
            summary.append(", %d" % pending_w, style="yellow")
            summary.append(" pend", style="dim")
        summary.append("  |  tasks: ", style="dim")
        summary.append("%d" % len(self._active_tasks), style="green bold" if self._active_tasks else "dim")
        summary.append(" run", style="dim")
        summary.append(", %d" % self._total_completed, style="dim")
        summary.append(" done", style="dim")

        active_line = Text()
        if self._active_tasks:
            names = [t.get("name", "?") for t in self._active_tasks[:5]]
            active_line.append("  active: ", style="dim")
            active_line.append(", ".join(names), style="bold")
            if len(self._active_tasks) > 5:
                active_line.append(" (+%d)" % (len(self._active_tasks) - 5), style="dim")
        else:
            active_line.append("  (no active tasks)", style="dim")

        return Group(Rule(style="dim"), summary, active_line)

    # -- full-screen redraw --

    def _redraw(self):
        """Perform a full-screen redraw.

        Moves the cursor to the home position and prints the layout.
        Because the Layout is sized to the terminal height and each
        line is padded to the terminal width, every cell on the screen
        is overwritten -- no ghost content from previous frames.
        """
        out = self._console.file
        out.write(_CURSOR_HOME)
        out.flush()
        self._console.print(self._render(), end="")

    # -- main loop --

    async def run(self, socket_path: str):
        """Connect to daemon and drive the TUI.

        Uses the alternate screen buffer with explicit full redraws
        (cursor-home + print) instead of Rich ``Live`` to avoid
        differential-rendering artifacts when the content structure
        changes between frames.
        """
        reader, writer = await asyncio.open_unix_connection(socket_path)

        self._start_time = time.monotonic()

        # Fetch initial status snapshot before subscribing
        await self._fetch_initial_status(reader, writer)

        # Subscribe to event stream
        sub = json.dumps({"method": "monitor.subscribe", "id": "mon"}) + "\n"
        writer.write(sub.encode())
        await writer.drain()
        resp = await reader.readline()
        _log.debug("Subscribe response: %s", resp.decode().strip())

        # Put stdin into raw mode so we get single keypresses
        stdin_fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(stdin_fd)

        # Key queue fed by the event loop's reader callback on stdin
        key_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _on_stdin_ready():
            try:
                ch = sys.stdin.read(1)
                if ch:
                    key_queue.put_nowait(ch)
            except Exception:
                pass

        out = self._console.file
        try:
            tty.setcbreak(stdin_fd)
            # Enter alternate screen and hide cursor
            out.write(_ENTER_ALT_SCREEN + _HIDE_CURSOR)
            out.flush()
            loop.add_reader(stdin_fd, _on_stdin_ready)

            # Initial draw
            self._redraw()

            while True:
                read_task = asyncio.ensure_future(reader.readline())
                key_task = asyncio.ensure_future(key_queue.get())

                done, pending = await asyncio.wait(
                    [read_task, key_task],
                    timeout=REFRESH_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()

                should_quit = False

                for task in done:
                    if task is read_task:
                        line = task.result()
                        if not line:
                            should_quit = True
                            break
                        event = parse_event(line.decode())
                        if event:
                            self._handle_event(event)
                    elif task is key_task:
                        ch = task.result()
                        if ch in ("q", "Q", "\x03"):  # q or Ctrl-C
                            should_quit = True

                if should_quit:
                    break

                self._redraw()

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            loop.remove_reader(stdin_fd)
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
            # Restore cursor and leave alternate screen
            out.write(_SHOW_CURSOR + _LEAVE_ALT_SCREEN)
            out.flush()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _fetch_initial_status(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Ask the daemon for a status snapshot so the display is populated
        before any events arrive."""
        req = json.dumps({"method": "status.get", "id": "init_status"}) + "\n"
        writer.write(req.encode())
        await writer.drain()

        try:
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        except asyncio.TimeoutError:
            return
        if not line:
            return
        try:
            resp = json.loads(line.decode())
        except json.JSONDecodeError:
            return

        result = resp.get("result", {})
        for w in result.get("workers", []):
            self._update_worker(w)
