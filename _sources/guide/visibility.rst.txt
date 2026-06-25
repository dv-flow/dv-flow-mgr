###############
Task Visibility
###############

Task visibility controls which tasks are exposed as entry points, which are
accessible across package boundaries, and which are internal implementation
details. The visibility system helps package authors create clean APIs while
hiding internal complexity.

Visibility Scopes
=================

DV Flow Manager supports three visibility scopes that can be assigned to tasks:

.. list-table:: Visibility Scopes
   :header-rows: 1
   :widths: 15 85

   * - Scope
     - Description
   * - ``root``
     - Task is an executable entry point. Shown in task listing when running ``dfm run`` without arguments.
   * - ``export``
     - Task is visible outside the package. Other packages can reference this task in their ``needs`` lists.
   * - ``local``
     - Task is only visible within its declaration fragment (e.g., within a task body or fragment file).

Tasks without any scope specifier have **package visibility** - they can be 
referenced by other tasks in the same package but are not shown as entry points
and will generate a warning if referenced from other packages.

Specifying Scope
================

There are two ways to specify task visibility:

Using the scope Field
---------------------

The ``scope`` field can be a single string or a list of scopes:

.. code-block:: yaml

    tasks:
    # Single scope
    - name: build
      scope: root
      run: make build
    
    # Multiple scopes
    - name: public_entry
      scope: [root, export]
      desc: "Public entry point visible to other packages"
      run: ./run.sh

Using Inline Scope Markers
--------------------------

For convenience, you can use ``root:``, ``export:``, or ``local:`` instead of
``name:`` to simultaneously name the task and set its scope:

.. code-block:: yaml

    tasks:
    # Equivalent to name: build + scope: root
    - root: build
      run: make build
    
    # Equivalent to name: format + scope: export
    - export: format
      run: format.sh
    
    # Equivalent to name: helper + scope: local
    - local: helper
      run: echo "internal"

Both inline markers and explicit ``scope:`` can be combined:

.. code-block:: yaml

    tasks:
    # root inline marker + scope: export = both root and export
    - root: main
      scope: export
      run: ./main.sh

Only one of ``name:``, ``root:``, ``export:``, ``local:``, or ``override:`` 
can be specified per task.

Root Scope
==========

Tasks marked with ``scope: root`` are **executable entry points**. When you run 
``dfm run`` without specifying a task, only root tasks are displayed:

.. code-block:: yaml

    package:
      name: my_project
      
      tasks:
      - root: build
        desc: "Build the project"
        run: make build
      
      - root: test
        desc: "Run tests"
        needs: [build]
        run: make test
      
      - name: internal_helper
        run: echo "helper"

Running ``dfm run`` without arguments:

.. code-block:: bash

    $ dfm run
    No task specified. Available Tasks:
    my_project.build  - Build the project
    my_project.test   - Run tests

Note that ``internal_helper`` is not shown because it lacks ``scope: root``.

.. note::
   Any task can still be run directly by name, regardless of visibility.
   Visibility only affects what is *listed*, not what is *runnable*.

Export Scope
============

Tasks marked with ``scope: export`` are **visible outside the package**. This is
essential for creating reusable packages where other packages depend on your tasks.

.. code-block:: yaml

    # utils/flow.yaml
    package:
      name: utils
      
      tasks:
      - export: format
        desc: "Format source files"
        run: format.sh
      
      - name: check_syntax
        run: check.sh

.. code-block:: yaml

    # main/flow.yaml
    package:
      name: main
      imports:
      - utils/flow.yaml
      
      tasks:
      - name: build
        needs:
        - utils.format     # OK - format is export
        - utils.check_syntax  # WARNING - not marked export

When a task references a non-export task from another package, DV Flow Manager
issues a warning:

.. code-block:: text

    Warning: Task 'main.build' references task 'utils.check_syntax' 
    in package 'utils' that is not marked 'export'

This warning helps identify unintended dependencies on internal implementation
details of other packages.

Local Scope
===========

Tasks marked with ``scope: local`` are only visible within their declaration
context. This is useful for helper tasks in compound task bodies:

.. code-block:: yaml

    tasks:
    - name: process_files
      body:
      - local: prepare
        run: ./prepare.sh
      
      - local: transform
        needs: [prepare]
        run: ./transform.sh
      
      - name: finalize
        needs: [transform]
        run: ./finalize.sh

Local tasks cannot be referenced from outside their containing body or fragment.

Default Package Visibility
==========================

Tasks without any scope specifier have **package visibility**:

* Can be referenced by other tasks in the same package
* Can be run directly by fully-qualified name
* Are NOT shown in task listings (``dfm run`` without arguments)
* Generate a warning if referenced from other packages

.. code-block:: yaml

    package:
      name: my_pkg
      
      tasks:
      - name: internal_task
        run: echo "package-visible only"
      
      - root: public_entry
        needs: [internal_task]  # OK - same package
        run: echo "entry point"

Combining Scopes
================

Scopes can be combined for tasks that serve multiple purposes:

.. code-block:: yaml

    tasks:
    # Entry point AND visible to other packages
    - name: main
      scope: [root, export]
      run: ./main.sh
    
    # Or using inline marker plus scope field
    - root: main
      scope: export
      run: ./main.sh

Common combinations:

* ``[root, export]`` - Public entry point (both CLI and API)
* ``root`` alone - Entry point only for this package (not for dependents)
* ``export`` alone - API for other packages, but not a primary entry point

Best Practices
==============

Entry Point Selection
---------------------

Mark tasks as ``root`` when they represent meaningful operations a user would
run directly:

.. code-block:: yaml

    tasks:
    # Good: Clear entry points
    - root: build
      desc: "Build the project"
    - root: test
      desc: "Run all tests"
    - root: clean
      desc: "Clean build artifacts"
    
    # Not root: Implementation details
    - name: compile_rtl
    - name: compile_tb
    - name: link

API Design
----------

For reusable packages, carefully consider which tasks to export:

.. code-block:: yaml

    package:
      name: my_library
      
      tasks:
      # Export: Stable API that users should depend on
      - export: compile
        desc: "Compile with library settings"
      
      # Not export: Internal implementation
      - name: gather_sources
      - name: process_includes
      
      # Export with root: Both API and entry point
      - root: test
        scope: export
        desc: "Run library self-tests"

Compound Task Organization
--------------------------

Use local scope for helper tasks that should not leak outside:

.. code-block:: yaml

    tasks:
    - name: full_flow
      rundir: inherit
      body:
      # Local helpers - not visible outside
      - local: step1
        run: ./step1.sh
      
      - local: step2
        needs: [step1]
        run: ./step2.sh
      
      # Final step produces output
      - name: result
        needs: [step2]
        uses: std.FileSet
        with:
          include: "*.out"

Warning Resolution
------------------

If you see warnings about referencing non-export tasks:

1. **If intentional**: Mark the referenced task as ``export``
2. **If unintentional**: Refactor to not depend on internal tasks
3. **If transitional**: Add TODO comment and plan to fix

.. code-block:: yaml

    # Before: Warning about using internal task
    - name: my_task
      needs: [other_pkg.internal_task]
    
    # After: Either export the task or restructure
    # Option 1: Ask other_pkg maintainer to export it
    # Option 2: Restructure to use exported task
    - name: my_task
      needs: [other_pkg.public_api]

Visibility in Fragments
=======================

Visibility works the same way in package fragments:

.. code-block:: yaml

    # src/rtl/flow.yaml
    fragment:
      tasks:
      - root: compile_rtl
        desc: "Compile RTL"
        run: ./compile_rtl.sh
      
      - name: helper
        run: ./helper.sh

All visibility rules apply across the entire package, including all fragments.

Task Listing Behavior Summary
=============================

+------------------+------------+------------+------------+
| Scope            | In Listing | Cross-Pkg  | Direct Run |
+==================+============+============+============+
| root             | Yes        | Warning    | Yes        |
+------------------+------------+------------+------------+
| export           | No         | Yes        | Yes        |
+------------------+------------+------------+------------+
| [root, export]   | Yes        | Yes        | Yes        |
+------------------+------------+------------+------------+
| local            | No         | No         | Limited    |
+------------------+------------+------------+------------+
| (none)           | No         | Warning    | Yes        |
+------------------+------------+------------+------------+

* **In Listing**: Shown by ``dfm run`` without arguments
* **Cross-Pkg**: Can be referenced in ``needs`` from another package
* **Direct Run**: Can be executed by name

