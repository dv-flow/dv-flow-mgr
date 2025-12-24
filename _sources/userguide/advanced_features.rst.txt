##################
Advanced Features
##################

This guide covers advanced DV Flow Manager features for complex workflows
and optimization. These patterns are useful for large projects, sophisticated
build systems, and performance-critical scenarios.

Task Override Patterns
======================

Selective Override
------------------

Override specific tasks based on conditions without affecting others:

.. code-block:: yaml

    package:
      name: my_project
      with:
        use_fast_sim:
          type: bool
          value: false
      
      tasks:
      - name: sim
        uses: hdlsim.vlt.SimImage
        with:
          optimization: "O2"
      
      configs:
      - name: fast
        with:
          use_fast_sim:
            value: true
        tasks:
        - name: sim_fast
          override: sim
          with:
            optimization: "O0"
            fast_mode: true

Layered Overrides
-----------------

Build override layers for different scenarios:

.. code-block:: yaml

    package:
      name: project
      
      configs:
      - name: base_debug
        tasks:
        - name: compile_debug
          override: compile
          with:
            debug: true
            optimization: "O0"
      
      - name: instrumented
        uses: base_debug
        tasks:
        - name: compile_instrumented
          override: compile
          with:
            debug: true
            optimization: "O0"
            coverage: true
            profiling: true

Each configuration builds on previous ones, adding more specialized behavior.

Conditional Override
--------------------

Combine overrides with conditions for dynamic behavior:

.. code-block:: yaml

    package:
      name: project
      with:
        platform:
          type: str
          value: "linux"
      
      tasks:
      - name: toolchain_linux
        override: toolchain
        iff: ${{ platform == "linux" }}
        uses: toolchains.gcc
      
      - name: toolchain_windows
        override: toolchain
        iff: ${{ platform == "windows" }}
        uses: toolchains.msvc

Dynamic Task Generation
========================

Programmatic Graph Construction
--------------------------------

Generate complex task graphs programmatically:

.. code-block:: python

    def GenerateTestSuite(ctxt, input):
        """Generate tests from a configuration file."""
        import json
        
        # Read test configuration
        config_file = os.path.join(ctxt.srcdir, "tests.json")
        with open(config_file) as f:
            tests = json.load(f)
        
        # Generate a task for each test
        for test in tests:
            test_task = ctxt.mkTaskNode(
                "hdlsim.vlt.SimRun",
                name=ctxt.mkName(f"test_{test['name']}"),
                plusargs=[f"+test={test['name']}"],
                seed=test.get('seed', 0)
            )
            ctxt.addTask(test_task)

Use in YAML:

.. code-block:: yaml

    tasks:
    - name: test_suite
      strategy:
        generate:
          run: my_pkg.test_gen.GenerateTestSuite

Parameterized Generation
------------------------

Use generator parameters to control graph structure:

.. code-block:: python

    def GenerateParallelTasks(ctxt, input):
        """Generate N parallel tasks."""
        count = input.params.task_count
        mode = input.params.mode
        
        for i in range(count):
            task = ctxt.mkTaskNode(
                "std.Exec",
                name=ctxt.mkName(f"task_{i}"),
                command=f"./process.sh {mode} {i}"
            )
            ctxt.addTask(task)

.. code-block:: yaml

    tasks:
    - name: parallel_work
      with:
        task_count:
          type: int
          value: 10
        mode:
          type: str
          value: "fast"
      strategy:
        generate:
          run: my_pkg.GenerateParallelTasks

Dependency Management
---------------------

Create complex dependency patterns dynamically:

.. code-block:: python

    def GeneratePipeline(ctxt, input):
        """Generate a pipeline of dependent tasks."""
        stages = input.params.stages
        prev_task = None
        
        for i, stage in enumerate(stages):
            needs = [prev_task] if prev_task else None
            task = ctxt.mkTaskNode(
                stage['type'],
                name=ctxt.mkName(stage['name']),
                needs=needs,
                **stage.get('params', {})
            )
            ctxt.addTask(task)
            prev_task = task

Complex Dataflow Patterns
==========================

Fan-Out/Fan-In
--------------

Distribute work across multiple tasks and collect results:

.. code-block:: yaml

    tasks:
    # Fan-out: One task produces data for many
    - name: source
      uses: std.FileSet
      with:
        include: "*.sv"
    
    # Multiple parallel consumers
    - name: lint
      uses: linter.Check
      needs: [source]
    
    - name: compile
      uses: hdlsim.vlt.SimImage
      needs: [source]
    
    - name: synthesize
      uses: synth.Build
      needs: [source]
    
    # Fan-in: Collect results
    - name: report
      uses: reports.Summary
      needs: [lint, compile, synthesize]

Selective Dataflow
------------------

Filter data items based on type or attributes:

.. code-block:: yaml

    tasks:
    - name: all_sources
      uses: std.FileSet
      with:
        include: "*.sv"
        attributes: [rtl, testbench]
    
    - name: compile_rtl
      uses: hdlsim.vlt.SimImage
      needs: [all_sources]
      consumes:
      - type: std.FileSet
        attributes: [rtl]
    
    - name: compile_tb
      uses: hdlsim.vlt.SimImage
      needs: [all_sources]
      consumes:
      - type: std.FileSet
        attributes: [testbench]

Data Transformation Pipeline
-----------------------------

Chain transformations with selective passthrough:

.. code-block:: yaml

    tasks:
    - name: gather_sources
      uses: std.FileSet
      with:
        include: "*.v"
    
    - name: transform
      uses: preprocessor.Transform
      needs: [gather_sources]
      passthrough: none  # Don't pass original sources forward
    
    - name: compile
      uses: hdlsim.vlt.SimImage
      needs: [transform]
      # Receives only transformed sources

Performance Optimization
========================

Parallel Execution Control
---------------------------

Control parallelism at different levels:

.. code-block:: yaml

    package:
      name: optimized_build
      
      tasks:
      # Parallel file processing
      - name: process_files
        strategy:
          matrix:
            file: ["a.v", "b.v", "c.v", "d.v"]
        body:
        - name: process
          uses: std.Exec
          with:
            command: "./process.sh ${{ matrix.file }}"
      
      # Sequential critical section
      - name: critical_task
        uses: my_tool.CriticalOp
        needs: [process_files]

Run with controlled parallelism:

.. code-block:: bash

    dfm run process_files -j 4  # Max 4 parallel tasks

Incremental Build Strategies
-----------------------------

Optimize incremental builds with smart dependencies:

.. code-block:: yaml

    tasks:
    - name: generated_code
      uses: std.Exec
      with:
        command: "./generate.sh"
        timestamp: "generated/timestamp.txt"
      uptodate: my_pkg.CheckGeneratorInputs
    
    - name: compile
      uses: hdlsim.vlt.SimImage
      needs: [generated_code]
      # Only recompiles if generated_code changed

Custom up-to-date check:

.. code-block:: python

    async def CheckGeneratorInputs(ctxt):
        """Check if generator inputs changed."""
        import glob
        import os
        
        # Get list of input files
        input_pattern = os.path.join(ctxt.srcdir, "templates/*.tmpl")
        input_files = glob.glob(input_pattern)
        
        # Compare with saved list
        saved_files = ctxt.memento.get("input_files", [])
        if set(input_files) != set(saved_files):
            return False
        
        # Check timestamps
        for f in input_files:
            current_time = os.path.getmtime(f)
            saved_time = ctxt.memento.get(f"time_{f}")
            if saved_time is None or current_time != saved_time:
                return False
        
        return True

Caching and Reuse
-----------------

Structure flows to maximize reuse across runs:

.. code-block:: yaml

    tasks:
    # Expensive, rarely changing
    - name: third_party_libs
      uses: std.FileSet
      with:
        base: "external/libs"
        include: "*.a"
    
    # Frequently changing sources
    - name: project_sources
      uses: std.FileSet
      with:
        include: "src/*.sv"
    
    # Compile independently
    - name: lib_compile
      uses: hdlsim.vlt.CompileLibs
      needs: [third_party_libs]
    
    - name: src_compile
      uses: hdlsim.vlt.CompileSources
      needs: [project_sources]
    
    # Link together
    - name: link
      uses: hdlsim.vlt.Link
      needs: [lib_compile, src_compile]

The ``lib_compile`` task rarely re-executes, speeding up incremental builds.

Resource Management
===================

License Management
------------------

Serialize tasks that require limited licenses:

.. code-block:: yaml

    tasks:
    - name: synthesis_jobs
      strategy:
        matrix:
          design: ["top", "sub1", "sub2"]
      body:
      - name: synth
        uses: synth.Build
        with:
          design: ${{ matrix.design }}

Run with limited parallelism to respect license limits:

.. code-block:: bash

    dfm run synthesis_jobs -j 2  # Only 2 licenses available

Memory-Constrained Tasks
-------------------------

Sequence memory-intensive tasks:

.. code-block:: yaml

    tasks:
    # Mark memory-intensive tasks
    - name: big_sim_1
      uses: hdlsim.vlt.SimRun
      with:
        memory_intensive: true
    
    - name: big_sim_2
      uses: hdlsim.vlt.SimRun
      with:
        memory_intensive: true
      needs: [big_sim_1]  # Serialize to avoid OOM

Distributed Execution
---------------------

Structure flows for distributed execution:

.. code-block:: yaml

    tasks:
    # Independent regression tests
    - name: regression
      strategy:
        matrix:
          test: [...]  # 100+ tests
      body:
      - name: run_test
        uses: hdlsim.vlt.SimRun
        with:
          test: ${{ matrix.test }}

Each matrix instance can potentially run on a different machine in a
distributed build system.

Debugging Complex Flows
========================

Visualization
-------------

Generate and examine task graphs:

.. code-block:: bash

    # Generate graph
    dfm graph my_task -o debug.dot
    
    # View with GraphViz
    dot -Tpng debug.dot -o debug.png
    
    # Or use interactive viewer
    xdot debug.dot

Incremental Debugging
---------------------

Debug specific tasks in isolation:

.. code-block:: bash

    # Run just one task, forcing execution
    dfm run problem_task -f
    
    # Run with verbose output
    dfm run problem_task -f -v
    
    # Use log UI for detailed output
    dfm run problem_task -f -u log

Trace Analysis
--------------

Analyze execution traces to find bottlenecks:

1. Run with trace generation (automatic)
2. Load trace in Perfetto or Chrome
3. Identify:

   * Tasks with longest duration
   * Idle time between tasks
   * Parallel execution efficiency
   * Critical path in the build

Then optimize by:

* Breaking large tasks into smaller parallel tasks
* Reordering dependencies to enable earlier starts
* Caching expensive operations
* Distributing work more evenly
