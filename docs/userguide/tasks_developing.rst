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

See the :doc:`../pytask_api` documentation 
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

See the :doc:`../pytask_api` documentation
for more information about the Python task-graph generation API.


PyTask Class-Based API
======================

For more complex tasks, DV Flow Manager provides a class-based API using the
``PyTask`` base class. This approach provides better organization for tasks
with substantial logic or state.

Defining a PyTask
-----------------

A PyTask is defined as a dataclass that inherits from ``dv_flow.mgr.PyTask``:

.. code-block:: python

    from dv_flow.mgr import PyTask
    import dataclasses as dc

    @dc.dataclass
    class MyCompiler(PyTask):
        desc = "Compiles HDL sources"
        doc = """
        This task compiles HDL sources using a configurable compiler.
        Supports multiple file types and optimization levels.
        """
        
        @dc.dataclass
        class Params:
            sources: list = dc.field(default_factory=list)
            optimization: str = "O2"
            debug: bool = False
        
        async def __call__(self) -> str:
            # Access parameters via self.params
            print(f"Compiling {len(self.params.sources)} files")
            print(f"Optimization: {self.params.optimization}")
            
            # Access context via self._ctxt
            rundir = self._ctxt.rundir
            
            # Perform compilation work here
            # ...
            
            # Return None for pytask execution, or a string for shell execution
            return None

The ``__call__`` method is the main entry point and receives the task
context automatically through the ``_ctxt`` and ``_input`` fields.

Using PyTask in YAML
--------------------

Reference a PyTask class in your flow definition:

.. code-block:: yaml

    package:
      name: my_tools
      
      tasks:
      - name: compile
        shell: pytask
        run: my_package.my_module.MyCompiler
        with:
          sources:
            - src/file1.v
            - src/file2.v
          optimization: "O3"
          debug: true

The PyTask class provides several advantages:

* **Type safety**: Parameters are defined with Python type hints
* **Documentation**: Docstrings become part of the task documentation
* **Organization**: Related logic stays together in a class
* **Reusability**: Classes can inherit from other classes
* **Testing**: Easier to unit test than inline code

Returning Commands
------------------

A PyTask can return a shell command instead of executing directly:

.. code-block:: python

    @dc.dataclass
    class MyTool(PyTask):
        @dc.dataclass
        class Params:
            input_file: str
            output_file: str
        
        async def __call__(self) -> str:
            # Generate command string
            cmd = f"my_tool -i {self.params.input_file} -o {self.params.output_file}"
            return cmd

When a string is returned, DV Flow executes it as a shell command using
the configured shell (default: pytask for Python execution).


PyPkg Package Factory
=====================

For advanced use cases, DV Flow supports defining packages entirely in Python
using the ``PyPkg`` class. This enables dynamic package construction and
programmatic task registration.

Defining a PyPkg
----------------

.. code-block:: python

    from dv_flow.mgr import PyPkg, pypkg
    import dataclasses as dc

    @dc.dataclass
    class MyToolPackage(PyPkg):
        name = "mytool"
        
        @dc.dataclass
        class Params:
            version: str = "1.0"
            enable_debug: bool = False

The ``@pypkg`` decorator registers tasks with the package:

.. code-block:: python

    @pypkg(MyToolPackage)
    @dc.dataclass
    class Compile(PyTask):
        @dc.dataclass
        class Params:
            sources: list = dc.field(default_factory=list)
        
        async def __call__(self):
            # Task implementation
            pass

    @pypkg(MyToolPackage)
    @dc.dataclass  
    class Link(PyTask):
        @dc.dataclass
        class Params:
            objects: list = dc.field(default_factory=list)
        
        async def __call__(self):
            # Task implementation
            pass

PyPkg Benefits
--------------

Using PyPkg provides several advantages:

* **Code reuse**: Share common Python code across tasks
* **Dynamic generation**: Programmatically create task definitions
* **Type checking**: Full Python type checking for package definitions
* **Version control**: Package and task versions managed together
* **Testing**: Unit test entire packages in Python

PyPkg packages can be distributed as Python packages and installed via pip,
making them easy to share and version.

Note: PyPkg is an advanced feature. For most use cases, YAML-based package
definitions with PyTask implementations provide the right balance of
simplicity and power.
