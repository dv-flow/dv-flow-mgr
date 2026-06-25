############
Task Runners
############

Task graphs defined by DV Flow can be run in many ways. Because the topology
of task graphs is known before execution, task graphs can be evaluated both
statically and dynamically.

DFM supports pluggable *runner backends* that control where and how tasks
execute. By default all tasks run on the local machine using the built-in
jobserver. Additional runners (such as LSF or SLURM) can dispatch work to
remote compute nodes in a cluster. DFM defines the ``RunnerBackend`` interface
to enable support for multiple execution mechanisms; see
:doc:`/reference/runner_backend_api` for the backend API.

Selecting a Runner
==================

The runner can be selected in several ways (listed from lowest to
highest precedence):

1. **Config files** -- set ``runner.default`` or ``runner.type`` in any
   config layer (see below).
2. **Environment variable** -- ``DFM_RUNNER=lsf``
3. **CLI flag** -- ``dfm run --runner lsf``

If nothing is specified, the runner defaults to ``local``.

CLI Flags
---------

``--runner <name>``
    Select the runner backend by name (e.g. ``local``, ``lsf``).

``--runner-opt key=value``
    Pass a key/value option to the runner. May be specified multiple
    times. Currently supported keys: ``queue``, ``project``,
    ``bsub_cmd``.

Example::

    dfm run --runner lsf --runner-opt queue=regr_high my_task

Local vs Remote Runners
=======================

**Local runner** (``local``)
    Executes tasks in the current process using an in-process jobserver
    for parallelism control. This is the default and behaves identically
    to DFM without runner support.

**Remote runners** (``lsf``, ``slurm``, etc.)
    Dispatch tasks to worker processes running on cluster compute nodes.
    The runner manages a pool of workers, serializes tasks, and routes
    results back to the orchestrator. Remote runners require a daemon
    process (see `Daemon`_, below).

Configuration Hierarchy
=======================

Runner configuration is loaded from up to four layers, merged in order
(later layers override earlier ones for scalar fields; list fields are
accumulated across layers):

1. **Installation config** -- ``<sys.prefix>/etc/dfm/config.yaml`` or
   the path in ``DFM_INSTALL_CONFIG`` env var. Set by admins to provide
   organization-wide defaults (queues, resource classes, wrapper
   scripts).

2. **Site config** -- ``~/.config/dfm/site.yaml``. Per-user preferences
   (default runner, project strings).

3. **Project config** -- ``<project>/.dfm/config.yaml``. Project-specific
   tuning (pool sizes, queue overrides, resource classes).

4. **CLI / env** -- ``--runner``, ``--runner-opt``, ``DFM_RUNNER``.

See :doc:`/reference/runner_config` for a full field reference.

Available Runners
=================

+-----------+------------------------------------------------------------------+
| Name      | Description                                                      |
+===========+==================================================================+
| ``local`` | Default. In-process execution via the jobserver.                 |
+-----------+------------------------------------------------------------------+
| ``lsf``   | Dispatches tasks to LSF worker jobs (requires LSF tools).        |
+-----------+------------------------------------------------------------------+
| ``slurm`` | Placeholder for future SLURM support.                            |
+-----------+------------------------------------------------------------------+

Third-party runners can be registered via the ``dfm_runners`` entry
point hook in a Python package.

Daemon
======

The DFM daemon is a background process that manages a pool of worker
processes across multiple ``dfm run`` invocations. This amortizes the
startup cost of cluster job submission (LSF, SLURM) and keeps warm
workers available for immediate task dispatch. Remote runners rely on the
daemon to host their worker pool.

Starting the Daemon
-------------------

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
-------------------

::

    dfm daemon stop

Sends a shutdown request to the running daemon. All workers are
terminated and the state file is removed.

Checking Status
---------------

::

    dfm daemon status
    dfm daemon status --json

Displays the current state: PID, number of workers, pending tasks,
and worker details. Use ``--json`` for machine-readable output.

Auto-Discovery from ``dfm run``
-------------------------------

When ``dfm run --runner lsf`` is invoked, the runner backend
automatically looks for ``<project>/.dfm/daemon.json``:

1. If found and the PID is alive, ``dfm run`` connects to the daemon
   and proxies tasks through it. Workers are shared across all
   connected ``dfm run`` processes.

2. If not found, ``dfm run`` can start an ephemeral pool for the
   duration of the run (workers are terminated when ``dfm run`` exits).

Multi-Client Usage
------------------

The daemon accepts connections from multiple ``dfm run`` processes
simultaneously. Tasks from all clients are dispatched to the shared
worker pool. Each task result is routed back to the originating client.
This allows multiple regression runs to share a single warm pool.

Stale State Files
-----------------

If the daemon crashes without cleanup, a stale ``daemon.json`` may
remain. Both ``dfm daemon status`` and ``dfm run`` detect stale files
(by checking if the PID is alive) and handle them gracefully:

- ``dfm daemon status``: reports the file as stale
- ``dfm run``: removes the stale file and falls back to ephemeral mode
- ``dfm daemon start``: removes the stale file and starts fresh

Monitoring
----------

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
