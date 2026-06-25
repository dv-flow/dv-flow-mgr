################
Python Tasks
################

When a shell-script task (see :doc:`developing_tasks`) becomes unwieldy --
when you need loops and conditionals over structured data, want to manipulate
typed inputs and outputs directly, or need in-process access to DV Flow
services -- implement the task in Python instead. This chapter covers the
class-based Python authoring API; for the per-type API surface (``TaskRunCtxt``,
``TaskDataInput``, ``TaskDataResult``, and friends) see
:doc:`/reference/python_api`.

The simplest Python tasks (``shell: pytask`` with an inline or external
``run``) are introduced in :doc:`developing_tasks`. The sections below cover the
class-based ``PyTask`` API and the ``PyPkg`` package factory for larger,
reusable implementations.

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
