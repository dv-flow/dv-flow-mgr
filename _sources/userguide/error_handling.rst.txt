##############
Error Handling
##############

DV Flow Manager supports workflows where task failure is an expected outcome —
for example, running a regression suite and collecting results across all tests
regardless of individual test pass/fail status.  This section describes the
mechanisms that let compound tasks tolerate subtask failures, continue executing
independent siblings, and aggregate results with custom logic.

.. contents::
   :local:
   :depth: 2


The ``std.TaskFailure`` Item
============================

When a leaf task exits with a non-zero status, the framework automatically
appends a ``std.TaskFailure`` data item to that task's output.  The item
carries:

* ``task_name`` — the fully-qualified name of the task that failed
* ``status`` — the non-zero exit code
* ``markers`` — any diagnostic markers the task produced (errors, warnings)

``std.TaskFailure`` items propagate through skipped tasks just like any other
data item, so a compound task can inspect failures from anywhere in its
subtask graph — even for subtasks that were skipped because an earlier sibling
already failed.

Downstream tasks that are not specifically written to handle failures can
safely ignore ``std.TaskFailure`` items; they are filtered out by the default
compound aggregator before the compound's output is produced (see
`Default Aggregation`_ below).

.. note::

   ``std.TaskFailure`` is a framework-emitted item.  You do not declare or
   produce it yourself; it is added automatically whenever a leaf task returns
   a non-zero status code.


Controlling Failure Tolerance with ``max_failures``
====================================================

By default a compound task stops launching new subtasks as soon as any
subtask fails (fail-fast behaviour).  The ``max_failures`` field changes this:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Value
     - Behaviour
   * - ``-1`` *(default)*
     - No limit.  All independent subtasks run regardless of failures.
       Failures propagate to the overall run status.
   * - ``0``
     - Fail-fast (equivalent to the default behaviour without ``max_failures``).
   * - ``N > 0``
     - Stop launching new independent subtasks once *N* failures have
       accumulated.  Failures are **scoped** to the compound — they do not
       update the global run status unless the compound's ``on_error``
       callable propagates them.

Example — run all tests even when some fail:

.. code-block:: yaml

    tasks:
    - name: RunAllTests
      max_failures: -1
      body:
      - name: test1
        uses: mytools.RunTest
        with: {seed: 1}
      - name: test2
        uses: mytools.RunTest
        with: {seed: 2}
      - name: test3
        uses: mytools.RunTest
        with: {seed: 3}

Example — tolerate up to two failures before stopping:

.. code-block:: yaml

    tasks:
    - name: RunTests
      max_failures: 2
      body:
      - name: test1
        uses: mytools.RunTest
      - name: test2
        uses: mytools.RunTest
      - name: test3
        uses: mytools.RunTest


Custom Result Aggregation with ``on_error``
===========================================

When a compound task finishes, DV Flow Manager calls an *aggregation
callable* to decide the compound's final status and output items.  By default
the built-in aggregator is used (see `Default Aggregation`_).  Supply
``on_error`` to use your own:

.. code-block:: yaml

    tasks:
    - name: RunAllTests
      max_failures: -1
      on_error: myproject.test_utils.aggregate_results
      body:
      - name: test1
        uses: mytools.RunTest
      - name: test2
        uses: mytools.RunTest

The value of ``on_error`` must be a ``module:function`` path (using ``.`` as
separator) that resolves to an ``async`` callable with this signature:

.. code-block:: python

    async def aggregate_results(
        ctxt: TaskRunCtxt,
        input: CompoundRunInput,
    ) -> TaskDataResult:
        ...

``on_error`` is called *even when no subtask failed*, so it also serves as a
general compound post-processor.

.. note::

   ``on_error`` and ``max_failures`` work independently.  You can use either
   or both.  ``max_failures`` controls *when siblings stop running*;
   ``on_error`` controls *what status and output items the compound produces*.


Default Aggregation
-------------------

When ``on_error`` is not specified the framework uses a built-in aggregator
that:

1. OR-accumulates the ``status`` fields of all ``std.TaskFailure`` items.
2. Passes all other output items through unchanged.

This means that for ordinary compound tasks that do not specify ``on_error``,
``std.TaskFailure`` items are **consumed** by the compound and are not
visible to downstream tasks.  The compound's own exit status reflects
whether any subtask failed.


Writing an ``on_error`` Handler
================================

The handler receives a :class:`~dv_flow.mgr.CompoundRunInput` object
containing all the information it needs to produce a result.

.. code-block:: python

    from dv_flow.mgr import TaskDataResult, TaskMarker
    from dv_flow.mgr.task_data import CompoundRunInput, TaskFailure
    from dv_flow.mgr.task_run_ctxt import TaskRunCtxt


    async def aggregate_results(
        ctxt: TaskRunCtxt,
        input: CompoundRunInput,
    ) -> TaskDataResult:
        failures = [i for i in input.inputs
                    if getattr(i, "type", None) == "std.TaskFailure"]
        other    = [i for i in input.inputs
                    if getattr(i, "type", None) != "std.TaskFailure"]

        passed = sum(1 for t in input.subtasks if t.status == 0 and not t.skipped)
        failed = len(failures)
        skipped = sum(1 for t in input.subtasks if t.skipped)

        ctxt.info(f"Results: {passed} passed, {failed} failed, {skipped} skipped")

        if failures:
            ctxt.error(f"{failed} subtask(s) failed")

        # Propagate non-failure items; report status.
        return TaskDataResult(
            status=1 if failures else 0,
            output=other,
        )

Key points:

* Filter ``std.TaskFailure`` items out of ``input.inputs`` before passing
  items downstream — or include them deliberately if consumers expect them.
* ``input.subtasks`` provides per-subtask ``status``, ``skipped``, and
  ``name`` fields (see :class:`~dv_flow.mgr.task_data.SubtaskSummary`).
* The returned :class:`~dv_flow.mgr.TaskDataResult` ``status`` becomes the
  compound task's exit status.
* Use ``ctxt.info()``, ``ctxt.warning()``, and ``ctxt.error()`` to attach
  diagnostic markers to the compound's output.


Dynamic Subgraphs and ``max_failures``
=======================================

Tasks that build their subgraph dynamically at runtime (via
:meth:`~dv_flow.mgr.TaskRunCtxt.run_subgraph`) also support ``max_failures``:

.. code-block:: python

    async def run_tests(ctxt, input):
        tasks = [build_test_node(ctxt, seed) for seed in seeds]
        # Run all tests; failures do not abort siblings.
        await ctxt.run_subgraph(tasks, max_failures=-1)
        return TaskDataResult(status=0, output=[])

The ``max_failures`` parameter on ``run_subgraph`` behaves identically to the
YAML field: ``-1`` runs all independent tasks while still propagating
failures to the overall run status; ``N > 0`` stops after *N* failures and
scopes the failures so they do not update the global run status.

See also: :doc:`tasks_developing` for the full dynamic subgraph API.


Worked Example: Test Regression
================================

This example shows a compound task that runs a full test suite, tolerates all
failures, and produces a summary report.

.. code-block:: yaml

    package:
      name: myproject

      tasks:
      - name: RunRegression
        max_failures: -1
        on_error: myproject.regression.summarize
        body:
        - name: test_smoke
          uses: mytools.RunTest
          with: {suite: smoke}
        - name: test_functional
          uses: mytools.RunTest
          with: {suite: functional}
        - name: test_corner
          uses: mytools.RunTest
          with: {suite: corner_cases}

.. code-block:: python

    # myproject/regression.py
    from dv_flow.mgr import TaskDataResult
    from dv_flow.mgr.task_data import CompoundRunInput
    from dv_flow.mgr.task_run_ctxt import TaskRunCtxt


    async def summarize(ctxt: TaskRunCtxt, input: CompoundRunInput) -> TaskDataResult:
        failures = [i for i in input.inputs
                    if getattr(i, "type", None) == "std.TaskFailure"]
        passed  = sum(1 for t in input.subtasks
                      if t.status == 0 and not t.skipped)
        failed  = len(failures)
        skipped = sum(1 for t in input.subtasks if t.skipped)

        ctxt.info(f"Regression complete: {passed} passed / "
                  f"{failed} failed / {skipped} skipped")

        for f in failures:
            ctxt.error(f"FAILED: {f.task_name} (status={f.status})")

        return TaskDataResult(
            status=1 if failures else 0,
            output=[i for i in input.inputs
                    if getattr(i, "type", None) != "std.TaskFailure"],
        )
