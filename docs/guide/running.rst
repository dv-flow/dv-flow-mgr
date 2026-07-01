#############
Running Flows
#############

Once a flow is defined, ``dfm run`` builds and executes the task graph. This
chapter walks through the typical run workflow; see :doc:`/reference/cli` for
the exhaustive option reference.

Running tasks
=============

Invoke one or more tasks by name from a directory at or below your project's
``flow.yaml``:

.. code-block:: bash

    dfm run sim

``dfm`` searches upward for the project's ``flow.yaml``, builds the task graph
for the requested task(s) and their dependencies, and executes it. Request
several tasks at once by listing them:

.. code-block:: bash

    dfm run compile test lint

If you run ``dfm run`` with no task, ``dfm`` lists the available tasks in the
package.

Controlling execution
=====================

A few options come up constantly:

``-j N``
    Limit concurrency to ``N`` simultaneous tasks (default: all cores).

``-D NAME=VALUE``
    Override a parameter for this run. See :doc:`parameters` for the full
    syntax and resolution order.

``-c, --config NAME``
    Select a package configuration -- a named variant such as debug vs. release
    or an alternate tool chain. See :doc:`configurations`.

``--runner BACKEND``
    Choose where tasks execute (``local`` or a cluster backend such as
    ``lsf``). See :doc:`runners`.

For example, to run with four parallel jobs in the debug configuration:

.. code-block:: bash

    dfm run build -c debug -j 4

Re-running and forcing work
===========================

DV Flow tracks which tasks are up to date and skips work that does not need to
re-run. To override that behavior:

``-f, --force``
    Re-run all tasks, ignoring up-to-date checks (preserves the rundir).

``--clean``
    Remove the rundir before starting, forcing a complete rebuild.

See :doc:`incremental` for how up-to-date checking works and how to reuse a
prior build's artifacts with ``--base-rundir``.

Watching progress
=================

``-u, --ui {log,progress,tui}`` selects the console interface: plain ``log``
output (the default for non-terminals), live ``progress`` bars, or a
full-screen ``tui``. Add ``-v`` to also show tasks that were already up to
date.

Capturing diagnostics
=====================

For CI, where the rundir is ephemeral, write a self-contained diagnostics
bundle that can be published as a build artifact:

.. code-block:: bash

    dfm run sim.regress --report build/dfm-report

The report is assembled from each task's execution data, so it works for any
runner backend (local, daemon, or remote).

See Also
========

* :doc:`incremental` -- up-to-date checking and artifact reuse.
* :doc:`runners` -- selecting and configuring runner backends.
* :doc:`/reference/cli` -- the complete command reference.
