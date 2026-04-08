#****************************************************************************
#* cmd_daemon.py
#*
#* CLI handlers for dfm daemon start/stop/status.
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
import os
import subprocess
import sys
from typing import ClassVar

from ..daemon import Daemon, DAEMON_STATE_FILE, is_daemon_alive
from ..runner_config import load_runner_config


_log = logging.getLogger("CmdDaemon")


class CmdDaemon:
    """Dispatch to daemon subcommands."""

    def __call__(self, args):
        subcmd = getattr(args, "daemon_subcmd", None)
        if subcmd == "start":
            return self._start(args)
        elif subcmd == "stop":
            return self._stop(args)
        elif subcmd == "status":
            return self._status(args)
        else:
            print("Usage: dfm daemon {start|stop|status}", file=sys.stderr)
            return 1

    def _get_project_root(self, args):
        return getattr(args, "root", None) or os.getcwd()

    def _start(self, args):
        project_root = self._get_project_root(args)
        dfm_dir = os.path.join(project_root, ".dfm")
        state_path = os.path.join(dfm_dir, DAEMON_STATE_FILE)

        # Check if already running
        if is_daemon_alive(state_path):
            with open(state_path) as f:
                state = json.load(f)
            pid = state.get("pid", 0)
            if getattr(args, "monitor", False):
                # Attach monitor to existing daemon
                print("Daemon already running (pid=%d), attaching monitor..." % pid)
                return self._attach_monitor(state)
            print("Daemon already running (pid=%d)" % pid)
            return 0

        # Load runner config
        runner_config = load_runner_config(
            project_root=project_root,
            cli_runner=getattr(args, "runner", None),
        )

        pool_size = getattr(args, "pool_size", None)
        if pool_size is not None:
            runner_config.pool.max_workers = int(pool_size)

        use_monitor = getattr(args, "monitor", False)
        use_foreground = getattr(args, "foreground", False)

        if use_monitor or use_foreground:
            # Run in this process (foreground or with monitor TUI)
            daemon = Daemon(
                project_root=project_root,
                config=runner_config,
            )

        if use_monitor:
            # Start daemon + monitor together in the same event loop
            try:
                asyncio.run(self._start_with_monitor(daemon))
            except KeyboardInterrupt:
                pass
        elif use_foreground:
            print("Starting daemon (pid=%d)..." % os.getpid())
            try:
                asyncio.run(daemon.run())
            except KeyboardInterrupt:
                print("\nDaemon stopped by user")
        else:
            # Default: launch daemon in a detached background process
            return self._start_background(args, project_root, state_path)

        return 0

    def _start_background(self, args, project_root, state_path):
        """Fork a detached daemon subprocess and return immediately."""
        # Build the command to re-exec ourselves with --foreground
        cmd = [sys.executable, "-m", "dv_flow.mgr",
               "daemon", "start", "--foreground",
               "--root", project_root]

        runner = getattr(args, "runner", None)
        if runner:
            cmd.extend(["--runner", runner])

        pool_size = getattr(args, "pool_size", None)
        if pool_size is not None:
            cmd.extend(["--pool-size", str(pool_size)])

        # Open /dev/null for stdin/stdout/stderr so the child is fully
        # detached from the terminal.
        devnull = open(os.devnull, "r+b")
        log_path = os.path.join(project_root, ".dfm", "daemon.log")
        os.makedirs(os.path.join(project_root, ".dfm"), exist_ok=True)
        log_fp = open(log_path, "a")

        proc = subprocess.Popen(
            cmd,
            stdin=devnull,
            stdout=log_fp,
            stderr=log_fp,
            start_new_session=True,  # detach from controlling terminal
        )
        devnull.close()
        log_fp.close()

        # Wait briefly for the daemon to write its state file
        import time
        for _ in range(20):
            time.sleep(0.1)
            if is_daemon_alive(state_path):
                with open(state_path) as f:
                    state = json.load(f)
                pid = state.get("pid", 0)
                print("Daemon started (pid=%d)" % pid)
                return 0

        # Check if the process died
        if proc.poll() is not None:
            print("Error: daemon process exited immediately (rc=%d)" % proc.returncode,
                  file=sys.stderr)
            print("Check %s for details" % log_path, file=sys.stderr)
            return 1

        # Still running but no state file yet -- report PID and hope for the best
        print("Daemon started (pid=%d, waiting for ready...)" % proc.pid)
        return 0

    async def _start_with_monitor(self, daemon: Daemon):
        """Start the daemon as a background task, then attach the monitor."""
        from ..daemon_monitor import DaemonMonitor

        # Launch daemon in background
        daemon_task = asyncio.create_task(daemon.run())

        # Wait for daemon to be ready (socket file exists)
        for _ in range(40):  # up to 2 seconds
            await asyncio.sleep(0.05)
            if os.path.exists(daemon.socket_path):
                break
        else:
            print("Error: daemon socket did not appear", file=sys.stderr)
            daemon_task.cancel()
            return

        # Attach monitor
        monitor = DaemonMonitor()
        try:
            await monitor.run(daemon.socket_path)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            # When monitor exits (q / Ctrl-C), shut down the daemon too
            await daemon.shutdown()
            # Give daemon a moment to clean up
            await asyncio.sleep(0.2)
            daemon_task.cancel()
            try:
                await daemon_task
            except asyncio.CancelledError:
                pass

    def _attach_monitor(self, state: dict) -> int:
        """Attach monitor to an already-running daemon."""
        from ..daemon_monitor import DaemonMonitor

        socket_path = state.get("socket", "")
        if not socket_path:
            print("Error: daemon.json missing socket path", file=sys.stderr)
            return 1

        monitor = DaemonMonitor()
        try:
            asyncio.run(monitor.run(socket_path))
        except KeyboardInterrupt:
            pass
        return 0

    def _stop(self, args):
        project_root = self._get_project_root(args)
        state_path = os.path.join(project_root, ".dfm", DAEMON_STATE_FILE)

        if not os.path.isfile(state_path):
            print("No daemon running (no %s)" % state_path)
            return 1

        if not is_daemon_alive(state_path):
            print("Stale daemon.json found, removing")
            os.unlink(state_path)
            return 0

        # Connect and send shutdown
        with open(state_path) as f:
            state = json.load(f)
        socket_path = state.get("socket", "")

        async def do_stop():
            try:
                reader, writer = await asyncio.open_unix_connection(socket_path)
                msg = json.dumps({"method": "shutdown", "id": "stop"}) + "\n"
                writer.write(msg.encode())
                await writer.drain()
                resp = await reader.readline()
                writer.close()
                await writer.wait_closed()
                return True
            except Exception as e:
                print("Error connecting to daemon: %s" % e, file=sys.stderr)
                return False

        success = asyncio.run(do_stop())
        if success:
            print("Daemon stopped (pid=%d)" % state.get("pid", 0))
        return 0 if success else 1

    def _status(self, args):
        project_root = self._get_project_root(args)
        state_path = os.path.join(project_root, ".dfm", DAEMON_STATE_FILE)
        use_json = getattr(args, "json", False)

        if not os.path.isfile(state_path):
            if use_json:
                print(json.dumps({"running": False}))
            else:
                print("No daemon running")
            return 1

        if not is_daemon_alive(state_path):
            if use_json:
                print(json.dumps({"running": False, "stale": True}))
            else:
                print("Stale daemon.json (PID not alive)")
            return 1

        with open(state_path) as f:
            state = json.load(f)

        # Try to get live status
        socket_path = state.get("socket", "")

        async def get_live_status():
            try:
                reader, writer = await asyncio.open_unix_connection(socket_path)
                msg = json.dumps({"method": "status.get", "id": "status"}) + "\n"
                writer.write(msg.encode())
                await writer.drain()
                resp_line = await reader.readline()
                writer.close()
                await writer.wait_closed()
                if resp_line:
                    return json.loads(resp_line.decode())
                return None
            except Exception:
                return None

        live = asyncio.run(get_live_status())

        if use_json:
            output = {"running": True, **state}
            if live and "result" in live:
                output.update(live["result"])
            print(json.dumps(output, indent=2))
        else:
            print("Daemon running (pid=%d)" % state.get("pid", 0))
            print("  Socket: %s" % socket_path)
            print("  Runner: %s" % state.get("runner", "unknown"))
            print("  Started: %s" % state.get("started", "unknown"))
            if live and "result" in live:
                r = live["result"]
                print("  Workers: %d" % len(r.get("workers", [])))
                print("  Pending tasks: %d" % r.get("pending_tasks", 0))
                for w in r.get("workers", []):
                    print("    - %s (%s) [%s] %s" % (
                        w.get("worker_id", ""),
                        w.get("hostname", ""),
                        w.get("state", ""),
                        w.get("current_task", "") or "",
                    ))
        return 0
