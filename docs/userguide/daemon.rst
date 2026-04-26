######
Daemon
######

The DFM daemon is a background process that manages a pool of worker
processes across multiple ``dfm run`` invocations. This amortizes the
startup cost of cluster job submission (LSF, SLURM) and keeps warm
workers available for immediate task dispatch.

Starting the Daemon
===================

::

    dfm daemon start

The daemon writes its state to ``<project>/.dfm/daemon.json`` and
listens for client connections on a Unix socket at
``<project>/.dfm/daemon.sock``.

Options:

``--runner <name>``
    Runner backend to use (e.g. ``local``, ``lsf``).

``--pool-size <n>``
    Maximum number of worker processes.

``--monitor``
    Attach the monitor TUI after starting (see below).

Stopping the Daemon
===================

::

    dfm daemon stop

Sends a shutdown request to the running daemon. All workers are
terminated and the state file is removed.

Checking Status
===============

::

    dfm daemon status
    dfm daemon status --json

Displays the current state: PID, number of workers, pending tasks,
and worker details. Use ``--json`` for machine-readable output.

Auto-Discovery from ``dfm run``
===============================

When ``dfm run --runner lsf`` is invoked, the runner backend
automatically looks for ``<project>/.dfm/daemon.json``:

1. If found and the PID is alive, ``dfm run`` connects to the daemon
   and proxies tasks through it. Workers are shared across all
   connected ``dfm run`` processes.

2. If not found, ``dfm run`` can start an ephemeral pool for the
   duration of the run (workers are terminated when ``dfm run`` exits).

Multi-Client Usage
==================

The daemon accepts connections from multiple ``dfm run`` processes
simultaneously. Tasks from all clients are dispatched to the shared
worker pool. Each task result is routed back to the originating client.
This allows multiple regression runs to share a single warm pool.

Stale State Files
=================

If the daemon crashes without cleanup, a stale ``daemon.json`` may
remain. Both ``dfm daemon status`` and ``dfm run`` detect stale files
(by checking if the PID is alive) and handle them gracefully:

- ``dfm daemon status``: reports the file as stale
- ``dfm run``: removes the stale file and falls back to ephemeral mode
- ``dfm daemon start``: removes the stale file and starts fresh


Monitoring
==========

Attach a live TUI to a running daemon::

    dfm daemon --monitor

Or start the daemon with the monitor attached::

    dfm daemon start --monitor

The monitor layout follows the style of Unix top:

- **Main area** (fills the screen): a scrolling table of currently
  running tasks showing the task name, assigned worker, host, and
  elapsed time. Below that, a "Recent Completions" table shows the
  last few finished tasks with pass/fail status.

- **Status bar** (fixed at the bottom, 4 lines): aggregate stats
  updated in real time:

  - Daemon uptime
  - Workers: total, busy, idle, pending
  - Tasks: currently running, total completed

Pressing q or Ctrl-C detaches the monitor; the daemon and its
workers continue running.
