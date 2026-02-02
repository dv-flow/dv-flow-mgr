##################
Dataflow & Produces
##################

DV Flow Manager uses **dataflow dependencies** to connect tasks together. Each task can:

* **Consume** input data from its dependencies
* **Produce** output data for dependent tasks

The ``produces`` feature allows tasks to declare what output datasets they create,
enabling workflow validation and task discovery.

Overview
========

When a task lists another task in its ``needs``, it receives the output data from
that dependency as input. To ensure compatibility and help with task discovery,
tasks should declare:

* **produces** - What output datasets this task creates
* **consumes** - What input datasets this task accepts

Example:

.. code-block:: yaml

    package:
      name: my_flow
      tasks:
        # Producer declares what it outputs
        - name: VerilogCompiler
          produces:
            - type: std.FileSet
              filetype: verilog
          run: |
            # ... compile verilog files
            
        # Consumer declares what it needs
        - name: Simulator
          needs: [VerilogCompiler]
          consumes:
            - type: std.FileSet
              filetype: verilog
          run: |
            # ... run simulation

The validator checks that ``VerilogCompiler``'s produces matches ``Simulator``'s
consumes, warning if there's a mismatch.

Declaring Produces
==================

Basic Declaration
-----------------

Declare output datasets using a list of pattern dictionaries:

.. code-block:: yaml

    - name: MyTask
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "produce verilog files"

Each pattern describes one type of output. Tasks can produce multiple types:

.. code-block:: yaml

    - name: Compiler
      produces:
        - type: std.FileSet
          filetype: verilog
        - type: std.FileSet
          filetype: verilogInclude
        - type: custom.BuildLog
          format: json

Parameter References
--------------------

Produces patterns can reference task parameters using ``${{ }}`` syntax:

.. code-block:: yaml

    - name: GenericProducer
      with:
        output_type:
          type: str
          value: verilog
      produces:
        - type: std.FileSet
          filetype: "${{ params.output_type }}"
      run: echo "produce ${{ output_type }} files"

The parameter reference is evaluated when the task graph is built, creating
a concrete produces pattern for that task instance.

Complex Patterns
----------------

Produces patterns can have multiple attributes to precisely describe outputs:

.. code-block:: yaml

    - name: VendorTool
      produces:
        - type: std.FileSet
          filetype: verilog
          vendor: synopsys
          version: "2023.09"
          optimization: speed
      run: echo "vendor-specific output"

Optional Declaration
--------------------

Declaring produces is **optional**. Tasks without produces are assumed to have
unknown or dynamic outputs, which is acceptable for validation:

.. code-block:: yaml

    # No produces declared - that's OK
    - name: DynamicTask
      run: echo "outputs vary at runtime"
    
    # Explicitly declare no outputs
    - name: SideEffectTask
      produces: []
      run: echo "only side effects, no data output"

Inheritance
===========

When a task uses another task as a base, it **inherits and extends** the base
task's produces patterns:

.. code-block:: yaml

    - name: BaseCompiler
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "base compilation"
    
    - name: AdvancedCompiler
      uses: BaseCompiler
      produces:
        - type: std.FileSet
          filetype: coverage
          format: ucdb
      run: echo "advanced compilation with coverage"

``AdvancedCompiler`` produces **both**:

1. ``std.FileSet`` with ``filetype: verilog`` (inherited from base)
2. ``std.FileSet`` with ``filetype: coverage`` (added by derived task)

This matches the principle that derived tasks add capabilities to base tasks.

Validation
==========

The ``dfm validate`` command checks produces/consumes compatibility between
connected tasks.

Compatibility Rules
-------------------

Two tasks are compatible when:

1. **Consumer has consumes: all** - Accepts any produces
2. **Producer has no produces** - Unknown outputs assumed compatible
3. **OR Logic** - If ANY consumer pattern matches ANY producer pattern, the
   dataflow is valid

Pattern Matching
----------------

A consumer pattern matches a producer pattern when:

* All attributes in the consumer pattern exist in the producer pattern
* All attribute values match exactly
* Producer can have additional attributes (subset matching)

Examples:

✅ **Compatible - Exact Match**:

.. code-block:: yaml

    # Producer
    produces:
      - type: std.FileSet
        filetype: verilog
    
    # Consumer  
    consumes:
      - type: std.FileSet
        filetype: verilog

✅ **Compatible - Subset Match**:

.. code-block:: yaml

    # Producer has extra attributes
    produces:
      - type: std.FileSet
        filetype: verilog
        vendor: synopsys
    
    # Consumer only requires some attributes
    consumes:
      - type: std.FileSet
        filetype: verilog

⚠️ **Warning - Mismatch**:

.. code-block:: yaml

    # Producer
    produces:
      - type: std.FileSet
        filetype: verilog
    
    # Consumer needs different type
    consumes:
      - type: std.FileSet
        filetype: vhdl  # Mismatch!

OR Logic Example
----------------

When multiple patterns exist, ANY match makes it valid:

.. code-block:: yaml

    # Producer outputs both verilog and vhdl
    - name: MultiProducer
      produces:
        - type: std.FileSet
          filetype: verilog
        - type: std.FileSet
          filetype: vhdl
    
    # Consumer accepts either
    - name: FlexibleConsumer
      needs: [MultiProducer]
      consumes:
        - type: std.FileSet
          filetype: verilog  # This matches, so it's valid!
        - type: std.FileSet
          filetype: systemverilog

Warnings vs Errors
------------------

Dataflow mismatches generate **warnings**, not errors. This allows:

* Flexible workflows during development
* Dynamic outputs not known at definition time
* Gradual adoption of produces declarations

To see validation warnings:

.. code-block:: bash

    $ dfm validate
    Package: my_flow
      Tasks: 5
      Types: 2
    
    Warnings (1):
      WARNING: Task 'Consumer' consumes [{'type': 'std.FileSet', 'filetype': 'vhdl'}]
               but 'Producer' produces [{'type': 'std.FileSet', 'filetype': 'verilog'}].
               No consume pattern matches any produce pattern.
    
    ✓ Validation passed
      (1 warning(s))

Task Discovery
==============

The ``show`` command can filter tasks by their produces patterns.

Finding Tasks by Output
-----------------------

Use ``--produces`` to find tasks that produce specific outputs:

.. code-block:: bash

    # Find tasks that produce verilog files
    $ dfm show tasks --produces "type=std.FileSet,filetype=verilog"
    
    Task                              Description
    ────────────────────────────────────────────────────
    my_flow.VerilogCompiler          Compiles Verilog RTL
    my_flow.PreProcessor             Preprocesses sources

Viewing Task Details
--------------------

The ``show task`` command displays produces information:

.. code-block:: bash

    $ dfm show task VerilogCompiler
    
    Task:        my_flow.VerilogCompiler
    Package:     my_flow
    Base:        -
    Scope:       -
    
    Parameters:
      optimization  str     O2    Optimization level
    
    Produces:
      - type=std.FileSet, filetype=verilog, optimization=O2
    
    Direct Needs:
      - my_flow.SourceFiles

Filter Syntax
-------------

The produces filter uses comma-separated key=value pairs:

.. code-block:: bash

    # Single attribute
    --produces "type=std.FileSet"
    
    # Multiple attributes (all must match)
    --produces "type=std.FileSet,filetype=verilog"
    
    # Complex filter
    --produces "type=std.FileSet,filetype=verilog,vendor=synopsys"

JSON Output
-----------

For programmatic use, add ``--json``:

.. code-block:: bash

    $ dfm show tasks --produces "type=std.FileSet" --json
    
.. code-block:: json

    {
      "command": "show tasks",
      "filters": {
        "produces": "type=std.FileSet"
      },
      "results": [
        {
          "name": "my_flow.VerilogCompiler",
          "package": "my_flow",
          "desc": "Compiles Verilog RTL",
          "produces": [
            {"type": "std.FileSet", "filetype": "verilog"}
          ]
        }
      ]
    }

Best Practices
==============

When to Declare Produces
-------------------------

✅ **Do declare produces for:**

* Tasks with predictable, structured outputs
* Tasks that produce FileSet or custom data items
* Reusable library tasks
* Tasks where output type matters to consumers

❌ **Don't declare produces for:**

* Tasks with purely side effects (no data outputs)
* Tasks with highly dynamic outputs not known until runtime
* Quick one-off tasks in a specific workflow

Being Specific
--------------

More specific produces patterns enable better validation:

.. code-block:: yaml

    # Less helpful - too generic
    produces:
      - type: std.FileSet
    
    # Better - includes key characteristics
    produces:
      - type: std.FileSet
        filetype: verilog
        stage: compiled
    
    # Best - fully describes the output
    produces:
      - type: std.FileSet
        filetype: verilog
        stage: compiled
        vendor: synopsys
        optimization: speed

Documenting Outputs
-------------------

Use task description and documentation to explain produces:

.. code-block:: yaml

    - name: AdvancedCompiler
      desc: Compiles Verilog with vendor-specific optimizations
      doc: |
        This task compiles Verilog RTL using vendor-specific tools,
        producing optimized netlists and optional coverage databases.
        
        Outputs:
        - Compiled Verilog netlist (optimized for speed)
        - UCDB coverage database (if coverage enabled)
      produces:
        - type: std.FileSet
          filetype: verilog
          optimization: speed
        - type: std.FileSet
          filetype: coverage
          format: ucdb

Common Patterns
===============

File Transformation Pipeline
----------------------------

.. code-block:: yaml

    tasks:
      - name: PreProcess
        produces:
          - type: std.FileSet
            filetype: verilog
            stage: preprocessed
        run: echo "preprocess"
      
      - name: Compile
        needs: [PreProcess]
        consumes:
          - type: std.FileSet
            filetype: verilog
        produces:
          - type: std.FileSet
            filetype: verilog
            stage: compiled
        run: echo "compile"
      
      - name: Optimize
        needs: [Compile]
        consumes:
          - type: std.FileSet
            filetype: verilog
            stage: compiled
        produces:
          - type: std.FileSet
            filetype: verilog
            stage: optimized
        run: echo "optimize"

Multi-Output Tasks
------------------

.. code-block:: yaml

    - name: BuildAndAnalyze
      produces:
        - type: std.FileSet
          filetype: executable
        - type: std.FileSet
          filetype: coverage
          format: lcov
        - type: std.FileSet
          filetype: log
      run: |
        # Build creates executable, coverage data, and logs

Parameterized Outputs
---------------------

.. code-block:: yaml

    - name: GenericBuilder
      with:
        target:
          type: str
          value: debug
        format:
          type: str
          value: elf
      produces:
        - type: std.FileSet
          filetype: executable
          target: "${{ params.target }}"
          format: "${{ params.format }}"
      run: echo "build for ${{ target }}"

Troubleshooting
===============

Validation Warnings
-------------------

**Problem**: Getting dataflow mismatch warnings

**Solutions**:

1. Check produces pattern matches consumes:

   .. code-block:: bash

       $ dfm show task ProducerTask
       $ dfm show task ConsumerTask

2. Make produces more specific or consumes less specific

3. Verify parameter values are correct

4. Check task inheritance - derived tasks extend produces

**Problem**: Warning says "No consume pattern matches any produce pattern"

**Solution**: This means NONE of the consumer's patterns match ANY of the
producer's patterns. Check for typos in attribute names or values.

Missing Produces
----------------

**Problem**: Tasks not appearing in ``--produces`` filter

**Solutions**:

1. Verify produces is declared in task definition
2. Check produces patterns match filter exactly
3. Ensure task is in the loaded package

.. code-block:: bash

    # Debug: show all tasks to verify it exists
    $ dfm show tasks
    
    # Debug: show specific task to see its produces
    $ dfm show task MyTask

Parameter Evaluation
--------------------

**Problem**: Parameter references not being evaluated

**Solutions**:

1. Use correct syntax: ``${{ params.name }}`` not ``${{ name }}``
2. Verify parameter is defined in task's ``with`` section
3. Check parameter has a value (default or override)

.. code-block:: yaml

    - name: MyTask
      with:
        output_type:
          type: str
          value: verilog  # Must have a value!
      produces:
        - type: std.FileSet
          filetype: "${{ params.output_type }}"

See Also
========

* :doc:`tasks_using` - Using and customizing tasks
* :doc:`tasks_developing` - Creating new tasks
* :doc:`expressions` - Parameter and expression syntax
* :doc:`../cmdref` - Command reference for validate and show
