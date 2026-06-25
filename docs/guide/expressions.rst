###########
Expressions
###########

DV Flow Manager supports dynamic parameter evaluation using the ``${{ }}``
expression syntax. Expressions allow parameters to reference other parameters,
perform calculations, and make decisions based on configuration values.

Expression Syntax
=================

Expressions are enclosed in ``${{ }}`` markers:

.. code-block:: yaml

    tasks:
    - name: message
      uses: std.Message
      with:
        msg: "Value is ${{ some_parameter }}"

Any parameter value can contain expressions. They are evaluated during
task graph elaboration, before any task execution begins.

Basic Usage
===========

Parameter References
--------------------

Reference package and task parameters by name:

.. code-block:: yaml

    package:
      name: my_pkg
      with:
        version:
          type: str
          value: "1.0"
        debug:
          type: bool
          value: false
      
      tasks:
      - name: build
        with:
          build_type:
            type: str
            value: "debug"
        uses: std.Message
        with:
          msg: "Building version ${{ version }} in ${{ build_type }} mode"

Expressions can reference:

* **Package parameters**: Defined in the package's ``with`` section
* **Task parameters**: Defined in the task's ``with`` section
* **Parent task parameters**: In compound tasks, access parent parameters

Arithmetic Operations
---------------------

Perform calculations within expressions:

.. code-block:: yaml

    package:
      name: example
      with:
        base_value:
          type: int
          value: 100
      
      tasks:
      - name: task1
        uses: std.Message
        with:
          msg: "Double value: ${{ base_value * 2 }}"
      
      - name: task2
        uses: std.Message
        with:
          msg: "Sum: ${{ base_value + 50 }}"

Supported operators:

* Arithmetic: ``+``, ``-``, ``*``, ``/``, ``//``, ``%``, ``**``
* Comparison: ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``
* Logical: ``and``, ``or``, ``not``

Boolean Expressions
-------------------

Use boolean expressions for conditional logic:

.. code-block:: yaml

    package:
      name: example
      with:
        debug:
          type: bool
          value: false
        optimization:
          type: int
          value: 2
      
      tasks:
      - name: check
        uses: std.Message
        iff: ${{ debug and optimization < 2 }}
        with:
          msg: "Debug mode with low optimization"

String Operations
-----------------

Concatenate strings and format values:

.. code-block:: yaml

    package:
      name: example
      with:
        prefix:
          type: str
          value: "build"
        version:
          type: str
          value: "1.0"
      
      tasks:
      - name: task1
        uses: std.Message
        with:
          msg: "${{ prefix }}_v${{ version }}"  # "build_v1.0"

Expression Contexts
===================

Package Scope
-------------

At package level, expressions can reference package parameters:

.. code-block:: yaml

    package:
      name: example
      with:
        compiler:
          type: str
          value: "gcc"
        version:
          type: str
          value: "11"
      
      imports:
      - name: toolchain
        with:
          compiler: ${{ compiler }}
          version: ${{ version }}

Task Scope
----------

Within tasks, expressions can access:

* Package parameters
* Task parameters
* Parent compound task parameters (if nested)

.. code-block:: yaml

    tasks:
    - name: parent
      with:
        mode:
          type: str
          value: "release"
      body:
      - name: child
        uses: std.Message
        with:
          # Access parent's 'mode' parameter
          msg: "Running in ${{ mode }} mode"

Matrix Variables
----------------

When using matrix strategy, expressions can reference matrix variables:

.. code-block:: yaml

    tasks:
    - name: test_suite
      strategy:
        matrix:
          test: ["test1", "test2", "test3"]
          seed: [100, 200, 300]
      body:
      - name: run_test
        uses: std.Message
        with:
          msg: "Running ${{ matrix.test }} with seed ${{ matrix.seed }}"

This generates 9 tasks (3 tests × 3 seeds) with appropriate parameter values.

Advanced Features
=================

Conditional Expressions
-----------------------

Use ternary-like conditional logic:

.. code-block:: yaml

    package:
      name: example
      with:
        debug:
          type: bool
          value: false
      
      tasks:
      - name: build
        shell: bash
        run: ${{ "make debug" if debug else "make release" }}

Note: Python-style conditional expressions (``x if condition else y``) are supported.

List and Dict Operations
-------------------------

Access list elements and dictionary values:

.. code-block:: yaml

    package:
      name: example
      with:
        flags:
          type: list
          value: ["-O2", "-Wall", "-Werror"]
        config:
          type: map
          value:
            arch: "x86_64"
            os: "linux"
      
      tasks:
      - name: task1
        uses: std.Message
        with:
          msg: "First flag: ${{ flags[0] }}"  # "-O2"
      
      - name: task2
        uses: std.Message
        with:
          msg: "Architecture: ${{ config['arch'] }}"  # "x86_64"

Function Calls
--------------

Limited set of built-in functions are available:

.. code-block:: yaml

    tasks:
    - name: example
      uses: std.Message
      with:
        msg: ${{ len(some_list) }}  # List length
        msg: ${{ str(some_int) }}   # Convert to string
        msg: ${{ int(some_str) }}   # Convert to integer

Available functions:

* ``len(x)``: Length of list/string
* ``str(x)``: Convert to string
* ``int(x)``: Convert to integer
* ``bool(x)``: Convert to boolean

Expression Evaluation Order
============================

Expressions are evaluated in the following order:

1. **Package load time**: Package-level expressions in imports and overrides
2. **Task elaboration**: Task parameter expressions
3. **Condition evaluation**: ``iff`` expressions for conditional tasks
4. **Matrix expansion**: Matrix variable substitution

This order ensures that:

* Configuration is resolved before task creation
* Parameters are available when needed
* Dependencies are properly evaluated

Runtime Expressions
===================

Expressions can reference runtime data from task dependencies using special variables:

* **inputs** - Outputs from dependency tasks (available at task runtime)
* **memento** - Cached data from previous run (for incremental builds)

These expressions are automatically **deferred** during graph construction and evaluated
when the task executes.

Example:

.. code-block:: yaml

    tasks:
      - name: producer
        scope: root
        produces: [std.FileSet]
        run: |
          echo '{"type":"std.FileSet","files":["a.sv","b.sv"]}'
        shell: bash
        
      - name: consumer
        scope: root
        needs: [producer]
        consumes: [std.FileSet]
        with:
          file_count:
            type: int
            value: "${{ inputs | length }}"
        run: |
          echo "Received ${file_count} inputs"
        shell: bash

The expression ``${{ inputs | length }}`` cannot be evaluated during graph construction
(inputs aren't known yet), so it's stored as a **deferred expression** and evaluated
when ``consumer`` runs, after ``producer`` completes.

Variable References
-------------------

Variables can be referenced using the ``$`` prefix for explicit variable references:

.. code-block:: yaml

    package:
      with:
        threshold:
          type: int
          value: 10
      
      tasks:
        - name: check
          with:
            result:
              value: "${{ $threshold * 2 }}"

This is particularly useful when working with filter parameters.

Array and Object Operations
----------------------------

Access array and object elements using indexing:

.. code-block:: yaml

    # Array indexing
    first_item: "${{ my_array[0] }}"
    second_item: "${{ my_array[1] }}"
    
    # Array slicing
    first_three: "${{ my_array[:3] }}"
    from_third: "${{ my_array[2:] }}"
    middle: "${{ my_array[2:5] }}"
    
    # Object field access
    value: "${{ config.settings.timeout }}"
    by_key: "${{ data['key_name'] }}"
    
    # Array iteration
    all_items: "${{ items[] }}"

JQ-Style Builtins
-----------------

Expressions support JQ-style builtin functions for data transformation using
the pipe operator ``|``:

.. code-block:: yaml

    # String operations
    parts: "${{ path | split(\"/\") }}"
    basename: "${{ path | split(\"/\") | last }}"
    extension: "${{ filename | split(\".\") | last }}"
    
    # Array operations
    count: "${{ items | length }}"
    sorted: "${{ values | sort }}"
    unique_vals: "${{ data | unique }}"
    reversed: "${{ list | reverse }}"
    first_val: "${{ items | first }}"
    last_val: "${{ items | last }}"
    
    # Type checking
    item_type: "${{ value | type }}"

Available builtins:

* ``length`` - Get length of array/object/string
* ``keys`` - Get keys of object
* ``values`` - Get values of object  
* ``sort`` - Sort array
* ``unique`` - Remove duplicates from array
* ``reverse`` - Reverse array
* ``first`` - Get first element
* ``last`` - Get last element
* ``flatten`` - Flatten nested arrays
* ``type`` - Get type name ("array", "object", "string", "number", "boolean", "null")
* ``split(sep)`` - Split string by separator

Chaining Operations
-------------------

Chain multiple operations using the pipe operator:

.. code-block:: yaml

    # Multiple builtins
    result: "${{ data | unique | sort | reverse }}"
    
    # Indexing with builtins
    last_unique: "${{ items | unique | last }}"
    
    # Complex pipeline
    filename: "${{ full_path | split(\"/\") | last }}"

Limitations
===========

Expressions have some limitations to maintain safety and predictability:

* **No side effects**: Expressions cannot modify state
* **No I/O**: Cannot read files or access network  
* **No arbitrary code**: Limited to safe expression subset

**Evaluation Phases:**

* **Static evaluation**: Most expressions evaluated during graph construction
* **Runtime evaluation**: Expressions referencing ``inputs`` or ``memento`` deferred until task execution

These limitations ensure that:

* Flow specifications remain declarative
* Task graphs can be analyzed before execution
* Flows are reproducible and predictable

Best Practices
==============

Keep Expressions Simple
------------------------

Prefer simple, readable expressions:

**Good:**

.. code-block:: yaml

    msg: "Version ${{ version }}"
    iff: ${{ debug }}

**Avoid:**

.. code-block:: yaml

    msg: ${{ "v" + str(major) + "." + str(minor) + ("_debug" if debug else "") }}

Use Parameters for Complex Logic
---------------------------------

Move complex logic into parameters rather than inline expressions:

**Good:**

.. code-block:: yaml

    package:
      with:
        full_version:
          type: str
          value: "${{ major }}.${{ minor }}${{ '_debug' if debug else '' }}"
      
      tasks:
      - name: build
        uses: std.Message
        with:
          msg: "Building version ${{ full_version }}"

Document Parameter Relationships
---------------------------------

When parameters depend on each other, document the relationships:

.. code-block:: yaml

    package:
      with:
        optimization:
          type: int
          value: 2
          doc: Optimization level (0-3)
        
        debug_symbols:
          type: bool
          value: false
          doc: |
            Enable debug symbols. Typically true when optimization is 0,
            false otherwise. Can be overridden explicitly.

Common Patterns
===============

Version Construction
--------------------

.. code-block:: yaml

    package:
      with:
        major:
          type: int
          value: 1
        minor:
          type: int
          value: 0
        patch:
          type: int
          value: 0
        version:
          type: str
          value: "${{ major }}.${{ minor }}.${{ patch }}"

Path Construction
-----------------

.. code-block:: yaml

    package:
      with:
        install_prefix:
          type: str
          value: "/opt/tools"
        tool_name:
          type: str
          value: "mytool"
        tool_path:
          type: str
          value: "${{ install_prefix }}/${{ tool_name }}"

Conditional Features
--------------------

.. code-block:: yaml

    package:
      with:
        enable_coverage:
          type: bool
          value: false
        enable_assertions:
          type: bool
          value: true
        debug_mode:
          type: bool
          value: "${{ enable_coverage or enable_assertions }}"

Parameter Selection
-------------------

.. code-block:: yaml

    package:
      with:
        simulator:
          type: str
          value: "verilator"
        debug_level:
          type: int
          value: 0
      
      tasks:
      - name: sim
        uses: std.Message
        with:
          msg: "Using simulator: ${{ simulator }} with debug=${{ debug_level }}"
