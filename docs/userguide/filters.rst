########
Filters
########

Filters provide a powerful way to transform and select data in expressions.
Inspired by Unix pipes and JQ, filters let you chain operations to process
inputs, parameter values, and other data.

Overview
========

A filter is a reusable transformation that can be applied to data using the
pipe operator ``|``. Filters can:

* Select items based on criteria (e.g., by file type)
* Transform data structures (e.g., extract field values)
* Aggregate information (e.g., count by type)

Example:

.. code-block:: yaml

    tasks:
      - name: compile
        needs: [find_sources]
        consumes: [std.FileSet]
        with:
          sv_files:
            value: "${{ inputs | by_filetype('.sv') }}"

The expression ``inputs | by_filetype('.sv')`` pipes the ``inputs`` array
through the ``by_filetype`` filter, which returns only items with ``.sv``
extensions.

Using Filters
=============

Basic Usage
-----------

Apply a filter using the pipe operator:

.. code-block:: yaml

    # Filter by file extension
    sv_files: "${{ inputs | by_filetype('.sv') }}"
    
    # Filter by type
    filesets: "${{ inputs | by_type('std.FileSet') }}"
    
    # Get all paths
    all_paths: "${{ inputs | paths }}"

Filters with Parameters
-----------------------

Some filters accept parameters:

.. code-block:: yaml

    # Filter by specific extension
    verilog: "${{ inputs | by_filetype('.v') }}"
    
    # Get first item of type
    first_fs: "${{ inputs | first_of_type('std.FileSet') }}"
    
    # Extract specific field
    types: "${{ inputs | pluck('type') }}"

Chaining Filters
----------------

Chain multiple filters for complex transformations:

.. code-block:: yaml

    # Get unique sorted extensions
    extensions: "${{ inputs | paths | extensions | unique | sort }}"
    
    # Get basenames of SystemVerilog files
    sv_names: "${{ inputs | by_filetype('.sv') | basenames }}"
    
    # Count then reverse
    data: "${{ values | sort | reverse }}"

Combining with Builtins
-----------------------

Filters work seamlessly with JQ-style builtins:

.. code-block:: yaml

    # Count filtered items
    sv_count: "${{ inputs | by_filetype('.sv') | length }}"
    
    # Get last path
    last_file: "${{ inputs | paths | last }}"
    
    # Split and filter
    basename: "${{ path | split('/') | last }}"

Defining Filters
================

Filters are defined at the package level using the ``filters`` key.

Basic Filter
------------

A simple filter without parameters:

.. code-block:: yaml

    package:
      name: myproject
      
      filters:
        - name: text_files
          export: true
          expr: |
            input[] | select(input.path | split(".") | last | . == "txt")

This filter iterates through ``input`` and selects items with ``.txt`` extensions.

Parameterized Filter
--------------------

Filters can accept parameters using ``with``:

.. code-block:: yaml

    filters:
      - name: by_pattern
        export: true
        with: [pattern]
        expr: |
          input[] | select(input.path | test($arg0))

Parameters are accessed as ``$arg0``, ``$arg1``, etc. (positional).

Usage:

.. code-block:: yaml

    matches: "${{ inputs | by_pattern('.*_test\\.sv') }}"

Executable Filters
------------------

Filters can execute Python or Shell scripts:

.. code-block:: yaml

    filters:
      - name: process_data
        export: true
        run: |
          import json
          import sys
          data = json.load(sys.stdin)
          result = [item for item in data if item['size'] > 1000]
          print(json.dumps(result))
        shell: python

The script receives data via stdin and outputs JSON via stdout.

Filter Visibility
=================

Filters support visibility modifiers:

Export
------

Make a filter available to importing packages:

.. code-block:: yaml

    filters:
      - name: public_filter
        export: true
        expr: "input[]"

Local
-----

Hide a filter from child packages:

.. code-block:: yaml

    filters:
      - name: internal_filter
        local: true
        expr: "input[]"

Default Visibility
------------------

By default, filters have ``name`` visibility (visible to package and children,
but not to importers).

.. code-block:: yaml

    filters:
      - name: package_filter
        expr: "input[]"

Qualified Names
---------------

Reference filters from other packages:

.. code-block:: yaml

    result: "${{ inputs | mypackage.custom_filter }}"

Standard Library Filters
========================

See :doc:`stdlib` for documentation of all standard library filters, including:

* ``by_filetype(ext)`` - Filter by file extension
* ``by_type(typename)`` - Filter by data type
* ``basenames`` - Extract filenames
* ``extensions`` - Extract file extensions
* ``paths`` - Get all paths from FileSets
* ``first_of_type(typename)`` - Get first item of type
* ``pluck(field)`` - Extract field values
* ``count_by_type`` - Count by type

Advanced Topics
===============

Runtime vs Static Evaluation
-----------------------------

Filters can be evaluated at different times:

**Static evaluation** (during graph construction):

.. code-block:: yaml

    # params is known at graph construction
    count: "${{ params | length }}"

**Runtime evaluation** (during task execution):

.. code-block:: yaml

    # inputs only known at runtime
    file_count: "${{ inputs | length }}"

Expressions referencing ``inputs`` or ``memento`` are automatically deferred
and evaluated at runtime.

Error Handling
--------------

Filters should handle missing or invalid data gracefully:

.. code-block:: yaml

    # Safe: returns empty array if no matches
    result: "${{ inputs | by_filetype('.sv') }}"
    
    # Safe: returns null if type not found
    first: "${{ inputs | first_of_type('MyType') }}"

Working with Types
------------------

Filters often work with data types. Access type information:

.. code-block:: yaml

    # Get type field
    types: "${{ inputs | pluck('type') }}"
    
    # Filter by type
    filesets: "${{ inputs | by_type('std.FileSet') }}"
    
    # Count by type
    counts: "${{ inputs | count_by_type }}"

Best Practices
==============

Keep Filters Simple
-------------------

Prefer simple, single-purpose filters:

.. code-block:: yaml

    # Good: focused filter
    - name: sv_files
      expr: "input[] | by_filetype('.sv')"
    
    # Better: reuse built-in
    sv_files: "${{ inputs | by_filetype('.sv') }}"

Use Descriptive Names
---------------------

Filter names should clearly indicate their purpose:

.. code-block:: yaml

    # Good names
    - name: verilog_sources
    - name: by_author
    - name: active_tasks
    
    # Avoid
    - name: filter1
    - name: process
    - name: do_stuff

Document Parameters
-------------------

When filters take parameters, document them:

.. code-block:: yaml

    filters:
      - name: files_larger_than
        # Parameters:
        #   size_kb: minimum file size in kilobytes
        with: [size_kb]
        expr: |
          input[] | select(input.size > ($arg0 * 1024))

Prefer Expression Filters
--------------------------

Use ``expr`` over ``run`` when possible:

* Expression filters are faster (no process spawn)
* Expression filters are more declarative
* Expression filters are easier to debug

Only use ``run`` for complex logic requiring full scripting language.

Test Your Filters
-----------------

Test filters with various inputs:

.. code-block:: yaml

    # Test with empty input
    result: "${{ [] | my_filter }}"
    
    # Test with single item
    result: "${{ [item] | my_filter }}"
    
    # Test with missing fields
    result: "${{ items_without_path | my_filter }}"

Known Limitations
=================

Current limitations of the filter system:

map() and select() Arguments
-----------------------------

The ``map()`` and ``select()`` builtins currently evaluate their arguments
before execution. This prevents per-item field access inside these operations:

.. code-block:: yaml

    # This does NOT work as expected:
    filtered: "${{ inputs | map(select(input.type == 'FileSet')) }}"
    
    # Workaround: use simpler filters
    filtered: "${{ inputs | by_type('FileSet') }}"

This is a known limitation and may be addressed in future versions.

Implicit Input Context
----------------------

Unlike native JQ, dv-flow uses explicit ``input`` variables rather than
implicit ``.`` context:

.. code-block:: yaml

    # JQ style (not supported):
    result: "${{ .[] | select(.type == 'A') }}"
    
    # dv-flow style (use explicit input):
    result: "${{ input[] }}"

Negative Array Indices
----------------------

Negative array indices are not currently supported:

.. code-block:: yaml

    # Not supported:
    last: "${{ array[-1] }}"
    
    # Use instead:
    last: "${{ array | last }}"

See Also
========

* :doc:`expressions` - Expression syntax and builtins
* :doc:`stdlib` - Standard library filters and tasks
* :doc:`dataflow` - Data flow and task dependencies
* :doc:`tasks_using` - Using tasks in flows
