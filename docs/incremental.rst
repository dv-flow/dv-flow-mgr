==================
Incremental Builds
==================

DV Flow Manager supports incremental builds by tracking task execution 
state and skipping tasks that are already up-to-date. This can significantly
reduce build times when only a subset of inputs have changed.

How It Works
============

Tasks record their inputs, outputs, and parameters in an ``exec.json`` file
in their run directory. On subsequent runs, DV Flow Manager checks:

1. **Exec record existence**: If no ``exec.json`` exists, the task must run.
2. **Parameter values**: If recorded parameters differ from current values, re-run.
3. **Input data**: If any input dataset is marked as 'changed', re-run.
4. **Input structure**: If the number, position, or elements of inputs differ, re-run.
5. **Custom up-to-date check**: If provided, invoke the custom method for final confirmation.

CLI Options
===========

The following CLI options control incremental build behavior:

``-f, --force``
    Force all tasks to run, ignoring up-to-date status. Useful when you 
    want to rebuild everything regardless of what has changed.

    .. code-block:: bash

        dfm run my_task --force

``-v, --verbose``
    Show all tasks including up-to-date ones. By default, tasks that are
    determined to be up-to-date are not displayed in the output. Use this
    option to see all tasks that were evaluated.

    .. code-block:: bash

        dfm run my_task --verbose

Custom Up-to-Date Methods
=========================

For tasks that reference files not explicitly listed in a fileset, you can
provide a custom up-to-date check method. The ``uptodate`` field in a task 
definition accepts one of three values:

- ``false``: Always run the task (never consider it up-to-date)
- A non-empty string: Python method to evaluate
- Empty/null: Use the default up-to-date check

YAML Configuration
------------------

.. code-block:: yaml

    tasks:
    - name: compile_sources
      uptodate: false  # Always recompile

    - name: check_dependencies
      uptodate: mymodule.check_deps_uptodate  # Custom check method

Implementing a Custom Check
---------------------------

A custom up-to-date method is an async Python function that receives an 
``UpToDateCtxt`` object and returns a boolean indicating whether the task
is up-to-date:

.. code-block:: python

    async def check_deps_uptodate(ctxt: UpToDateCtxt) -> bool:
        """
        Custom up-to-date check that verifies external dependencies.
        
        Returns True if task is up-to-date, False if it needs to run.
        """
        import os
        
        # Check if a specific file has been modified since last run
        dep_file = os.path.join(ctxt.rundir, "external_dep.txt")
        
        if not os.path.exists(dep_file):
            return False
        
        # Compare timestamps, checksums, etc.
        # ...
        
        return True

See :doc:`pytask_api` for complete documentation of the ``UpToDateCtxt`` class.

Task Output
===========

When a task is determined to be up-to-date, it is marked as such in the 
output:

.. code-block:: text

    << [1] Task mypackage.compile (up-to-date) 0.05ms

The previous output data is loaded from the task's ``exec.json`` file,
allowing downstream tasks to use cached results without re-executing.
