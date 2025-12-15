################
Developing Tasks
################

The `Using Tasks` chapter describes how to customize existing tasks by
specifying parameter values and using compound tasks to compose tasks 
from a collection of sub-tasks. When adding a new tool or capability, 
it's likely that more fine-grained control will be needed. In these
cases, it makes sense to provide a programming-language implementation
for a task.

Task Execution
==============

It is most common to provide an implementation for a task's execution
behavior. This is most-commonly done in Python, but shell scripts can
also be used. Tasks provide the `run` and `shell` parameters to specify
the implementation. 

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

See the `DV Flow Manager <https://dv-flow.github.io/dv-flow-mgr>`_ documentation 
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

See the `DV Flow Manager <https://dv-flow.github.io/dv-flow-mgr>`_ documentation
for more information about the Python task-graph generation API.
