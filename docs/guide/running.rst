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

Supplying an Input From the Command Line
========================================

``--needs TASK`` gives the task you are running an additional input, exactly as
if it appeared in that task's ``needs:``. It is the same edge, so it resolves
by the same (possibly partial) name, and its data reaches the task the same way.

This is what lets a task in one package consume an artifact from another without
either project listing the other. An analysis task that ships with a tool
package, and is deliberately not part of your project's run surface, is joined
to your artifact at invocation time:

.. code-block:: bash

    dfm run hdlsim.prof.Analyze --needs my-proj.sim-img.prof

The supplied name may be a variant cell (see :doc:`variants`), which is what
makes "analyze *the profiling build*" expressible.

Two properties worth relying on:

* **Additive.** It adds to what the task declares; it never replaces a declared
  dependency.
* **Root only.** It applies to the task named on the command line and to nothing
  nested inside it, so it cannot quietly rewire the middle of a flow.

``--needs`` may be repeated. An unresolvable name stops the run before anything
executes.

.. note::

   A command-line need is not type-checked against what the task expects. If
   the task declares what it requires, that check happens where every other
   dependency is checked -- not in the flag.

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

.. _run-results:

Run results
===========

Every run writes a record of what happened to
``rundir/out/<run-id>/results.json``, and ``rundir/out/latest`` points at the
newest one. The run-id is a local timestamp (``20261031-142210``); the last
line ``dfm run`` prints is the path:

.. code-block:: text

    Results: rundir/out/20261031-142210/results.json

The record is a tree of results, one node per test case, suite, synthesis stage
or task, each with a status, a headline, the checks that decided it, its
numbers, and its log and waveform. Read it with ``dfm show results``:

.. code-block:: bash

    dfm show results                 # the latest run, as a tree
    dfm show results --failures      # just what failed, with log lines
    dfm show results --list          # every recorded run, newest first
    dfm show results --run 20261031-142210
    dfm show results --json --failures   # the summary block, for scripts

Passing subtrees collapse to one line; a failing node shows its failing checks,
its first errors, and ``log: <path>:<line>``, so the next step is to open that
line. The ``summary`` block of ``results.json`` holds the same thing for a
program: ``.summary.status``, ``.summary.counts`` and ``.summary.failures``.

**A build failure shows up in the results.** When a task fails outside any
test -- a compile error, a code generator, a ``todo`` gate -- the tests that
needed it are listed as ``NOTRUN`` with ``blocked: <task> failed``, and the
failed task itself appears under ``_tasks`` with its error and its log:

.. code-block:: text

    tests  ERROR  1 of 4 errored, 2 not run
    ├─ uvm-tests  pass  [1 passed]
    ├─ soc-tests  NOTRUN
    │  ├─ soc-dma-copy  NOTRUN  blocked: wb-dma-example.fw-build failed
    │  └─ soc-dma-copy-two  NOTRUN  blocked: wb-dma-example.fw-build failed
    └─ _tasks  ERROR  1 task(s) failed outside any result
       └─ fw-build  ERROR  dma.c:41: error: 'DMA_CSR' undeclared
             log: rundir/wb-dma-example.fw-build/wb-dma-example.fw-build.log

A task that produces no result of its own (a build, a code generator) still
gets a record: dfm makes one from the task's status, its messages and its log.

The results tree
----------------

Next to ``results.json``, ``rundir/out/<run-id>/results/`` holds the same
record as directories, one per result, named as the results are (not as the
task directories are), so ``ls``, ``less`` and an editor are enough:

.. code-block:: text

    $ ls rundir/out/latest/results/
    FAILED  tests
    $ ls rundir/out/latest/results/FAILED/
    fw-build  soc-dma-copy  two-ch
    $ cat rundir/out/latest/results/FAILED/two-ch/STATUS
    fail: UVM_ERROR x2: ch1 dst mismatch @ 0x40
    check uvm_errors: fail (uvm_errors=2, want == 0)
    $ ls rundir/out/latest/results/tests/uvm-tests/two-ch/
    STATUS  log  sim.log  sim_stats.json  sim.time  waves.fst  ...
    $ less rundir/out/latest/results/FAILED/two-ch/log

Each directory has a ``STATUS`` file (the status, the headline, the failing
checks) and links every entry of its task's run directory under its own name,
plus ``log`` to its log, so a case's directory reads like its run directory
and a suite's holds its ``<task>.exec_data.json`` next to its children. A
child's directory takes precedence over a run-directory entry of the same
name. Files outside the run directory are linked by role: ``cov/...``,
``report-<label>``, ``<role>-<file>``. A node whose run directory no longer
exists links ``rundir`` to where it was. Because the tree links the task
logs, a walk over all of ``rundir/`` (``find rundir -name '*.log'``) sees each
log twice; skip ``rundir/out``. ``FAILED/`` links to everything the summary lists as a failure (a run
with no failures has no ``FAILED/``),
including the tasks under ``_tasks``. Links inside the tree are relative, so a
copied ``out/<run-id>`` keeps working; links into task directories are
absolute. On a file system without symlinks each directory gets a
``LINKS.txt`` instead. ``--no-results-tree`` (or ``results.tree: false``)
skips the tree.

Old records, stale files and retention
--------------------------------------

Task directories are reused from run to run -- that is what makes up-to-date
checks work -- so the waves an old record links to may have been overwritten
by a later run. Every artifact's mtime and size is recorded when the run
ends; ``dfm show results`` compares them with the file now and marks a changed
file ``[stale]`` and a deleted one ``[missing]`` (``--json`` adds ``state``
and ``stale``). The record itself is never rewritten.

Logs are small and are what people go back to, so ``results.copy_logs:
true`` copies every log into ``out/<run-id>/logs/`` and points the tree's
``log`` links at the copies; an old record then keeps its logs. Waves and
coverage databases are not copied.

After each run dfm keeps that run and the one before it
(``results.keep_previous: 1``) and removes older run directories. Raise it to
keep more history, set ``0`` to keep only the current run, or ``all`` to never
prune. Only timestamped (and older ``0001``-style) run directories are pruned
-- never one named with ``--run-id``, the current run, or ``latest``'s target,
and those do not count toward ``keep_previous``. A pruned run's
``std.Publish`` outputs go with it, since they live in the same directory. The settings live in the ``results:`` section of
``.dfm/config.yaml`` (see :doc:`/reference/results`).

``--no-results`` skips the record (for benchmarking dfm itself). The format is
described in :doc:`/reference/results`.

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
