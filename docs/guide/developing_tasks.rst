################
Developing Tasks
################

The `Using Tasks` chapter describes how to customize existing tasks by
specifying parameter values and using compound tasks to compose tasks
from a collection of sub-tasks. When adding a new tool or capability, you
will often need finer-grained control: a task that runs a specific command,
generates files, or invokes a tool. DV Flow lets you implement such a task
directly in the flow file.

The recommended starting point is a **shell-script task** -- you put the
commands in the task's ``run`` body and DV Flow handles scheduling, inputs,
outputs, and up-to-date tracking. When a script grows unwieldy -- when you
need rich control flow, typed data manipulation, or in-process access to DV
Flow APIs -- you can graduate the same task to a
:ref:`Python implementation <python-task-impl>`.

Task Execution
==============

A task selects its implementation with two parameters:

* ``run`` -- the body of the implementation (shell commands, or Python code /
  a Python entry-point reference).
* ``shell`` -- the interpreter for ``run``. ``bash`` (the default),
  ``shell``, ``csh``, and ``tcsh`` run ``run`` as a shell script;
  ``pytask`` runs it as Python.

If ``shell`` is omitted, the task is a shell-script task executed with
``bash``.

Shell-Script Tasks
==================

A shell-script task puts one or more shell commands in the ``run`` body. This
is the most direct way to wrap a tool or generate files, and it is the
recommended place to start.

.. code-block:: yaml

    package:
      name: my_tool
      tasks:
      - name: gen_rtl
        with:
          top:
            type: str
            value: top
        run: |
          mkdir -p rtl
          echo "module ${{ top }}(); endmodule" > rtl/${{ top }}.v
          echo "Generated rtl/${{ top }}.v"

The ``run`` body is written to a script and executed. ``${{ }}`` expressions
are substituted before the script runs, so ``${{ top }}`` above expands to the
value of the task's ``top`` parameter. Other useful expressions include
``${{ rundir }}`` (the task's run directory) and ``${{ this.<param> }}``.

You can select a different shell explicitly:

.. code-block:: yaml

    - name: report
      shell: bash
      run: |
        echo "Building in ${{ rundir }}"

Exchanging data with the dataflow graph
---------------------------------------

Shell tasks exchange data with the rest of the graph through a
GitHub-Actions-style contract: the runner passes **inputs as ``DFM_*``
environment variables** (parameters via ``DFM_PARAM_*``/``DFM_PARAMS``,
consumed inputs via ``DFM_INPUTS``, the run directory via ``DFM_RUNDIR``) and
collects **outputs from append-only files** the script writes -- produced
filesets (``DFM_OUTPUT``), environment/PATH additions (``DFM_ENV`` /
``DFM_PATH``), diagnostics (``DFM_MARKERS``), and the memento used for
up-to-date checks (``DFM_MEMENTO_OUT``). The ``dfm-out`` helper writes these
output files for you.

See :doc:`script_io` for the full input/output contract and the ``dfm-out``
reference.

.. _python-task-impl:

Python Task Implementation
==========================

When a shell script becomes unwieldy -- you need loops and conditionals over
structured data, want to manipulate typed inputs/outputs directly, or need
in-process access to DV Flow services -- implement the task in Python instead.
Set ``shell: pytask`` and provide the Python code inline, or reference an
external Python entry point.

External Pytask
---------------

A `pytask` implementation for a task is provided by a Python async method
that accepts input parameters from the DV Flow runtime system and returns
data to the system. When the `pytask` implementation is external, the
`run` parameter specifies the name of the Python method.

.. code-block:: yaml

    package:
      name: my_tool
      tasks:
      - name: my_task
        uses: my_package.MyTask
        shell: pytask
        run: my_package.my_module.MyTask
        with:
          msg:
            type: str

The task definition above specifies that a `pytask` implementation for the task
is provided by a Python method named `my_package.my_module.MyTask`.

.. code-block:: python3

    async def MyTask(ctxt, input):
        print("Message: %s" % input.params.msg)

See the :doc:`/reference/python_api` documentation
for more information about the Python API available to task implementations.

This "external" implementation makes the most sense when the task implementation
is moderately complex or lengthy.

Inline Pytask
-------------

When the task implementation is simple, the code can be in-lined within the YAML.

.. code-block:: yaml

    package:
      name: my_tool
      tasks:
      - name: my_task
        uses: my_package.MyTask
        with:
          msg:
            type: str
        shell: pytask
        run: |
          print("Message: %s" % input.params.msg)

When this task is executed, the body of the `run` entry will be evaluated as the
body of an async Python method that has `ctxt`, and `input` parameters.

Task-Graph Expansion
====================

Sometimes build flows need to run multiple variations of the same core step.
For example, we may wish to run multiple UVM tests that only vary in the
input arguments. The `matrix` strategy can work well in these cases.

.. code-block:: yaml
    
    package:
      name: my_pkg
      
      tasks:
      - name: SayHi
        strategy:
          matrix:
            who: ["Adam", "Mary", "Joe"]
        body:
          - name: Output
            uses: std.Message
            with:
              msg: "Hello ${{ matrix.who }}!"

The `matrix` strategy is only valid on compound tasks. The body tasks
are evaluated once for each combination of matrix variables. Body-task
parameters can reference the matrix variables. 

In this case, we would expect the `SayHi` task to look like this 
when expanded:

.. mermaid::

    flowchart TD
      A[SayHi.in]
      B[Hello Adam!]
      C[Hello Mary!]
      D[Hello Joe!]
      E[SayHi]
      A --> B
      A --> C
      A --> D
      B --> E 
      C --> E
      D --> E


Task-Graph Generation
=====================

It is sometimes useful to generate task graphs programmatically instead of 
capturing them manually or generating them textually in YAML. A `generate` 
strategy can be provided to algorithmically define a task subgraph.

Note that generation is done statically as part of graph elaboration. This 
means that the generated graph structure may only depend on values, such
as parameter values, that are known during elaboration. The graph structure
cannot be created using data conveyed as dataflow between tasks.

.. code-block:: yaml

    package:
      name: my_pkg
      
      tasks:
      - name: SayHi
        with:
          count:
            type: int
            value: 1
        strategy:
          generate: my_pkg.my_mod.GenGraph

The `generate` strategy specifies that the containing task will be a 
compound task whose sub-tasks are provided by the specified 
generator. As with other task implementations, the generator code can
be specified externally in a Python module or inline.

.. code-block:: python3

    def GenGraph(ctxt, input):
        count = input.params.count
        for i in range(count):
            ctxt.addTask(ctxt.mkTaskNode(
                "std.Message", with={"count": 1})
                name=ctxt.mkName("SayHi%d" % i), 
                msg="Hello World% %d!" % (i+1)))

See the :doc:`/reference/python_api` documentation
for more information about the Python task-graph generation API.


Task-Graph Generation and Error Handling
-----------------------------------------

Dynamically-generated subgraphs support the same ``max_failures`` control as
static compound tasks.  Pass ``max_failures`` to
:meth:`~dv_flow.mgr.TaskRunCtxt.run_subgraph` to control how many subtask
failures are tolerated before remaining independent siblings are skipped:

.. code-block:: python

    async def run_tests(ctxt, input):
        # Build test task nodes dynamically …
        tasks = [build_test_node(ctxt, seed) for seed in seeds]

        # Run all; failures do not abort siblings.
        await ctxt.run_subgraph(tasks, max_failures=-1)
        return TaskDataResult(status=0, output=[])

See :doc:`error_handling` for the full ``max_failures`` semantics.


For larger Python implementations -- the class-based ``PyTask`` API and the
``PyPkg`` package factory -- see :doc:`python_tasks`.


Template Tasks
==============

A template task defers expansion of its ``run`` expression from load time
to graph-build time.  This is useful for reusable building blocks whose
``run`` expression references variables that only exist in the use context
(matrix variables, compound parameters, package parameters of the
consuming package, etc.).

Declaring a Template Task
-------------------------

Add ``template: true`` to the task definition:

.. code-block:: yaml

    package:
      name: sim_pkg

      tasks:
      - name: CompileStub
        template: true
        shell: bash
        run: "echo Skipping compile for ${{ matrix.variant }}"
        passthrough: all
        consumes: none

The ``run`` string is stored verbatim at load time.  When the task is
instantiated (via ``uses:`` or as an override replacement), the graph
builder expands ``${{ }}`` expressions using the instantiation context.

Using a Template Task
---------------------

A template task is consumed through ``uses:``, just like any other task:

.. code-block:: yaml

    tasks:
    - name: MyCompile
      uses: sim_pkg.CompileStub

At graph-build time, ``${{ matrix.variant }}`` (or whichever variables
appear in ``run``) are resolved against the current context.

Template tasks work naturally inside ``strategy.matrix``:

.. code-block:: yaml

    tasks:
    - name: StubMatrix
      strategy:
        matrix:
          variant: [rtl, gate]
      body:
      - name: Step
        uses: sim_pkg.CompileStub

Each matrix cell gets its own expansion, so ``${{ matrix.variant }}``
resolves to ``rtl`` and ``gate`` respectively.

Constraints
-----------

* A template task **cannot be invoked directly** from the CLI or as a
  top-level entry point.  Doing so raises an error.
* ``template: true`` and ``override:`` are mutually exclusive on the same
  task definition.
* Parameter definitions (``with:``) are unaffected -- they are already
  expanded lazily at graph-build time regardless of the ``template`` flag.

When to Use Templates
---------------------

Use ``template: true`` when:

* The ``run`` expression references variables that are not available at
  load time (e.g. ``${{ matrix.variant }}``, ``${{ this.some_param }}``).
* You are building a reusable task that will be consumed by multiple
  packages with different parameter contexts.
* You need the same task definition to produce different shell commands
  depending on where it is instantiated.
