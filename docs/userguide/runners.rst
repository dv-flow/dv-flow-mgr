############
Task Runners
############

DFM supports pluggable *runner backends* that control where and how tasks
execute. By default all tasks run on the local machine using the built-in
jobserver. Additional runners (such as LSF or SLURM) can dispatch work to
remote compute nodes in a cluster.

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
    process (see :doc:`daemon`).

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
