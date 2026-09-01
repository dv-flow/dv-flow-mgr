################
Standard Library
################

The ``std`` package ships with DV Flow Manager and is imported by nearly every
flow file. It provides the tasks that move files around, the data types that
``produces:`` and ``consumes:`` speak in, and the filters expressions use.

.. note::

   **Every task, type and filter is documented in** :doc:`/reference/stdlib`,
   which is generated from ``std/flow.yaml``. Parameters, defaults, dataflow
   contracts and source locations all live there and cannot drift from the code.

   This page covers what generation cannot: which task to reach for, how the
   framework emits ``std.TaskFailure``, and how to write a filter of your own.

Choosing a task
===============

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - To do this
     - Use
   * - Collect source files by glob
     - :dvf:task:`std.FileSet`
   * - Write a file from inline content
     - :dvf:task:`std.CreateFile`
   * - Copy outputs into the run's output directory
     - :dvf:task:`std.Publish`
   * - Place different inputs differently under ``Publish``
     - :dvf:task:`std.PubSet`
   * - Set environment variables for downstream tasks
     - :dvf:task:`std.SetEnv`
   * - Re-tag an existing FileSet's filetype
     - :dvf:task:`std.SetFileType`
   * - Add include directories
     - :dvf:task:`std.IncDirs`
   * - Print a message
     - :dvf:task:`std.Message`
   * - Group other tasks without doing anything itself
     - :dvf:task:`std.Null`
   * - Run a suite of tests
     - :dvf:task:`std.TestRunner`
   * - Ask what a test runner offers
     - :dvf:task:`std.TestInfo`

To run a shell command you do not need a task at all -- see
`Running Shell Commands`_ below.

std.TaskFailure
===============

A framework-emitted data item that records a subtask failure.  ``std.TaskFailure``
is **never declared or produced directly by user tasks**; the framework appends
it to a leaf task's output whenever that task exits with a non-zero status.

``std.TaskFailure`` items propagate through skipped tasks so that an enclosing
compound task can observe all failures in its subtask graph via its
:class:`~dv_flow.mgr.task_data.CompoundRunInput`.

Fields
------

* **task_name** — Fully-qualified name of the task that failed
* **status** — The non-zero exit code returned by the task
* **markers** — Diagnostic markers (errors/warnings) produced by the task

Usage
-----

In an ``on_error`` handler, filter ``std.TaskFailure`` items from
``input.inputs`` to separate failure records from regular output:

.. code-block:: python

    failures = [i for i in input.inputs
                if getattr(i, "type", None) == "std.TaskFailure"]
    other    = [i for i in input.inputs
                if getattr(i, "type", None) != "std.TaskFailure"]

See :doc:`error_handling` for full details on compound task error handling.

Running Shell Commands
======================

Shell commands are executed by specifying ``shell: bash`` (or another shell)
and providing the command with ``run:``. This is useful for running external
tools, scripts, or commands that don't have dedicated task implementations.

Example
-------

.. code-block:: yaml

    package:
        name: exec.example
    
        tasks:
        - name: run_script
          shell: bash
          run: ./scripts/process_data.sh
        
        - name: inline_commands
          shell: bash
          run: |
            echo "Processing data..."
            ./scripts/process.sh
            echo "Done"

Shell Tasks
-----------

The ``shell:`` field selects the interpreter for the ``run:`` body. The
registered shells are:

* ``bash`` - Bourne Again Shell (the default)
* ``shell`` - alias for ``bash``
* ``csh`` - C shell
* ``tcsh`` - TENEX C shell
* ``pytask`` - run ``run:`` as Python with task context (for custom tasks)

The ``run:`` field specifies the command or script to execute. For inline
scripts, use YAML's multi-line syntax (``|`` or ``>``).


Filters
=======

The standard filters are documented in :doc:`/reference/stdlib`, generated from
``std/filters.yaml`` -- including each filter's signature, its arguments, and
the positions those arguments bind to.

.. warning::

   Filters are declared but **not yet resolved by the engine**: a package's
   filter registry is never handed to the expression evaluator, so using one in
   an expression currently fails. The generated reference says so on every
   filter entry.

Defining Custom Filters
========================

You can define custom filters in your package using JQ-style expressions:

.. code-block:: yaml

    package:
      name: myproject
      
      filters:
        - name: verilog_only
          export: true
          expr: |
            input[]
        
        - name: large_files
          export: true
          with: [size_kb]
          expr: |
            input[] | select(input.size > ($arg0 * 1024))

**Filter Properties:**

* ``name`` - Filter name (required)
* ``expr`` - JQ-style expression (for expression filters)
* ``run`` - Shell or Python script (for executable filters)
* ``with`` - Parameter names (positional, accessed as $arg0, $arg1, etc.)
* ``export`` - Make filter visible to importing packages (default: false)
* ``local`` - Hide filter from child packages (default: false)

For detailed filter documentation, see :doc:`filters`.
