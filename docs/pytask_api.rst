===============
Python Task API 
===============

DV Flow Manager provides two task-oriented API extension mechanisms that
allow leaf tasks to be implemented as a Python task and allow the body
of a compound task to be generated.

Leaf-Task Implementation API
============================

The core implementation for tasks is provided by a Python `async` method. 
This method is passed two parameters:

* `runner` - Services that the task runner provides for the use of tasks
* `input` - The input data for the task

The method must return a `TaskDataResult` object with the execution 
status of the task, result data, markers, and memento data.

TaskDataInput
-------------

An object of type `TaskDataInput` is passed as the `input` parameter 
of the runner method. 

.. autoclass:: dv_flow.mgr.TaskDataInput
   :members:
   :exclude-members: model_config

TaskDataItem
------------

Data is passed between tasks via `TaskDataItem`-derived objects. 
Each task may produce 0 or more `TaskDataItem` objects as output. 
A task receives all the `TaskDataItem` objects produced by its
dependencies. 

.. autoclass:: dv_flow.mgr.TaskDataItem
   :members:
   :exclude-members: model_config

TaskRunCtxt
-----------

The task implementaion is passed a task-run context object that
provides utilities for the task.

.. autoclass:: dv_flow.mgr.TaskRunCtxt
   :members:
   :exclude-members: model_config


TaskDataResult
--------------
Task implementation methods must return an object of type 
`TaskDataResult`. This object contains key data about 
task execution.

.. autoclass:: dv_flow.mgr.TaskDataResult
   :members:
   :exclude-members: model_config

TaskMarker
----------
Tasks may produce markers to highlight key information to the
user. A marker is typically a pointer to a file location with
an associated severity level (error, warning, info).


.. autoclass:: dv_flow.mgr.TaskMarker
   :members:
   :exclude-members: model_config

.. autoclass:: dv_flow.mgr.TaskMarkerLoc
   :members:
   :exclude-members: model_config

Task-Graph Generation API
=========================

DV flow manager supports the `generate` strategy by calling a Python
task that is responsible for building the body of the compound task.

A graph-building method has the following signature:

.. code-block:: python3

    def build_graph(ctxt : TaskGenCtxt, input : TaskGenInputData):
        pass

* **ctxt** - Provides services for building and registering tasks
* **input** - Input to the generator. Currently, the task parameters

Assuming that this method is defined in a module named `my_module`, 
the following YAML specifies that the task will be called to generate
the body of the compound task:

.. code-block:: YAML

    tasks:
    - name: mytask
      strategy:
        generate:
          run: my_module.build_graph


TaskGenCtxt API
---------------

.. autoclass:: dv_flow.mgr.TaskGenCtxt
    :members:
    :exclude-members: model_config

TaskGenInputData
----------------

The `TaskGenInputData` class provides the value of task parameters
specified on the containing compound task.

Custom Up-to-Date Check API
===========================

Tasks can define custom up-to-date check methods to determine whether 
a task needs to be re-executed. This is useful for tasks that reference 
files not explicitly listed in a fileset.

Implementing a Custom Check
---------------------------

A custom up-to-date method is an async Python function with the following
signature:

.. code-block:: python

    async def check_uptodate(ctxt: UpToDateCtxt) -> bool:
        """
        Check if task is up-to-date.
        
        Returns True if the task is up-to-date and should be skipped,
        False if the task needs to run.
        """
        pass

The method is specified in the task definition YAML:

.. code-block:: yaml

    tasks:
    - name: my_task
      uptodate: mymodule.check_uptodate
      run: mymodule.run_task

UpToDateCtxt
------------

The context object passed to custom up-to-date methods provides access
to the task's run directory, parameters, inputs, and previous execution data.

.. autoclass:: dv_flow.mgr.uptodate_ctxt.UpToDateCtxt
    :members:
    :exclude-members: model_config

Example: Checking File Timestamps
---------------------------------

Here's an example of a custom up-to-date check that verifies whether
an external dependency file has been modified:

.. code-block:: python

    import os
    from dv_flow.mgr.uptodate_ctxt import UpToDateCtxt

    async def check_external_deps(ctxt: UpToDateCtxt) -> bool:
        """Check if external dependency files are unchanged."""
        
        # Get the recorded timestamp from previous execution
        prev_mtime = ctxt.exec_data.get('dep_mtime')
        if prev_mtime is None:
            return False  # No previous data, must run
        
        # Check current timestamp
        dep_file = os.path.join(ctxt.rundir, "..", "external_deps.txt")
        if not os.path.exists(dep_file):
            return False  # Dependency missing, must run
        
        current_mtime = os.path.getmtime(dep_file)
        
        # Up-to-date if timestamp hasn't changed
        return current_mtime == prev_mtime

Example: Running a Subprocess Check
-----------------------------------

The ``UpToDateCtxt.exec()`` method allows running subprocesses for 
dependency checking:

.. code-block:: python

    from dv_flow.mgr.uptodate_ctxt import UpToDateCtxt

    async def check_git_status(ctxt: UpToDateCtxt) -> bool:
        """Check if git working tree is clean."""
        
        # Returns 0 if no changes, non-zero otherwise
        status = await ctxt.exec(["git", "diff", "--quiet", "HEAD"])
        
        return status == 0  # Up-to-date if no changes


PyTask Class API Reference
===========================

The ``PyTask`` class provides a class-based interface for implementing tasks
in Python. This approach offers better organization, type safety, and
reusability compared to function-based tasks.

PyTask Base Class
-----------------

.. autoclass:: dv_flow.mgr.PyTask
    :members:
    :exclude-members: model_config

Class Attributes
~~~~~~~~~~~~~~~~

* **desc** (str): Short description of the task
* **doc** (str): Full documentation for the task  
* **shell** (str): Shell to use for execution (default: "pytask")

Instance Attributes
~~~~~~~~~~~~~~~~~~~

* **_ctxt** (TaskRunCtxt): Task execution context (set by runtime)
* **_input** (TaskDataInput): Task input data (set by runtime)

Properties
~~~~~~~~~~

* **params**: Typed access to task parameters (returns instance of nested Params class)

Defining a PyTask
-----------------

.. code-block:: python

    from dv_flow.mgr import PyTask
    import dataclasses as dc
    
    @dc.dataclass
    class MyTask(PyTask):
        desc = "Brief description"
        doc = "Detailed documentation..."
        
        @dc.dataclass
        class Params:
            input_file: str = ""
            output_file: str = ""
            verbose: bool = False
        
        async def __call__(self) -> Union[str, None]:
            # Access parameters
            print(f"Processing {self.params.input_file}")
            
            # Access context
            rundir = self._ctxt.rundir
            
            # Execute commands
            status = await self._ctxt.exec(
                ["process", self.params.input_file],
                logfile="process.log"
            )
            
            # Return None for direct execution
            # Or return a command string to execute
            return None

Using PyTask
~~~~~~~~~~~~

Reference the PyTask class in YAML:

.. code-block:: yaml

    tasks:
    - name: my_task
      shell: pytask
      run: my_module.MyTask
      with:
        input_file: data.txt
        output_file: result.txt
        verbose: true


PyPkg Class API Reference
==========================

The ``PyPkg`` class enables defining entire packages in Python, providing
programmatic control over package structure and task registration.

PyPkg Base Class
----------------

.. autoclass:: dv_flow.mgr.PyPkg
    :members:
    :exclude-members: model_config

Class Attributes
~~~~~~~~~~~~~~~~

* **name** (str): Package name (optional, defaults to class name)

Methods
~~~~~~~

* **registerTask(cls, T)**: Register a task class with this package

Defining a PyPkg
----------------

.. code-block:: python

    from dv_flow.mgr import PyPkg, pypkg, PyTask
    import dataclasses as dc
    
    @dc.dataclass
    class MyToolPkg(PyPkg):
        name = "mytool"
        
        @dc.dataclass
        class Params:
            version: str = "1.0"
            debug: bool = False

Registering Tasks
~~~~~~~~~~~~~~~~~

Use the ``@pypkg`` decorator to register tasks:

.. code-block:: python

    @pypkg(MyToolPkg)
    @dc.dataclass
    class Compile(PyTask):
        @dc.dataclass
        class Params:
            sources: list = dc.field(default_factory=list)
        
        async def __call__(self):
            # Implementation
            pass

Tasks are automatically registered with the package and become available
as ``mytool.Compile`` in flow definitions.


Additional API Details
======================

TaskRunCtxt Extended API
------------------------

The ``TaskRunCtxt`` class provides additional methods for task implementations:

**mkDataItem(type, \*\*kwargs)**
    Create a data item of the specified type. Returns a configured data item
    instance that can be added to task outputs.
    
    .. code-block:: python
    
        fileset = ctxt.mkDataItem("std.FileSet")
        fileset.filetype = "verilogSource"
        fileset.files = ["file1.v", "file2.v"]

**exec(cmd, logfile=None, logfilter=None, cwd=None, env=None)**
    Execute a command and capture output. Returns the command's exit status.
    
    .. code-block:: python
    
        status = await ctxt.exec(
            ["gcc", "-o", "output", "input.c"],
            logfile="compile.log",
            cwd="/tmp/build"
        )

**error(msg), warning(msg), info(msg)**
    Add markers to the task output for user notification.
    
    .. code-block:: python
    
        ctxt.error("Compilation failed")
        ctxt.warning("Deprecated option used")
        ctxt.info("Processing 100 files")

**Properties:**
    * **rundir**: Task's run directory path
    * **root_pkgdir**: Root package directory  
    * **root_rundir**: Root run directory
    * **env**: Environment variables (dict)


TaskGenCtxt Extended API
------------------------

The ``TaskGenCtxt`` class provides methods for programmatic task graph generation:

**mkTaskNode(type_t, name=None, srcdir=None, needs=None, \*\*kwargs)**
    Create a new task node in the graph.
    
    .. code-block:: python
    
        node = ctxt.mkTaskNode(
            "std.Message",
            name="hello",
            msg="Hello, World!"
        )

**mkName(name)**
    Generate a qualified task name relative to the containing compound task.
    
    .. code-block:: python
    
        # Inside compound task "parent"
        name = ctxt.mkName("child")  # Returns "parent.child"

**addTask(task)**
    Add a task node to the generated graph.
    
    .. code-block:: python
    
        for i in range(5):
            task = ctxt.mkTaskNode("std.Message", msg=f"Task {i}")
            ctxt.addTask(task)

**Properties:**
    * **rundir**: Task's run directory path
    * **srcdir**: Source directory path
    * **basename**: Base name for generated tasks
    * **input**: Input task node
    * **builder**: Task graph builder instance