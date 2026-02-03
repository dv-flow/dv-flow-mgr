==================
Incremental Builds
==================

DV Flow Manager supports incremental builds by tracking task execution 
state and skipping tasks that are already up-to-date. This can significantly
reduce build times when only a subset of inputs have changed.

How It Works
============

Tasks record their inputs, outputs, and parameters in an ``exec.json`` file
in their run directory. On subsequent runs, DV Flow Manager checks:

1. **Exec record existence**: If no ``exec.json`` exists, the task must run.
2. **Parameter values**: If recorded parameters differ from current values, re-run.
3. **Input data**: If any input dataset is marked as 'changed', re-run.
4. **Input structure**: If the number, position, or elements of inputs differ, re-run.
5. **Custom up-to-date check**: If provided, invoke the custom method for final confirmation.

CLI Options
===========

The following CLI options control incremental build behavior:

``-f, --force``
    Force all tasks to run, ignoring up-to-date status. Useful when you 
    want to rebuild everything regardless of what has changed.

    .. code-block:: bash

        dfm run my_task --force

``-v, --verbose``
    Show all tasks including up-to-date ones. By default, tasks that are
    determined to be up-to-date are not displayed in the output. Use this
    option to see all tasks that were evaluated.

    .. code-block:: bash

        dfm run my_task --verbose

Custom Up-to-Date Methods
=========================

For tasks that reference files not explicitly listed in a fileset, you can
provide a custom up-to-date check method. The ``uptodate`` field in a task 
definition accepts one of three values:

- ``false``: Always run the task (never consider it up-to-date)
- A non-empty string: Python method to evaluate
- Empty/null: Use the default up-to-date check

YAML Configuration
------------------

.. code-block:: yaml

    tasks:
    - name: compile_sources
      uptodate: false  # Always recompile

    - name: check_dependencies
      uptodate: mymodule.check_deps_uptodate  # Custom check method

Implementing a Custom Check
---------------------------

A custom up-to-date method is an async Python function that receives an 
``UpToDateCtxt`` object and returns a boolean indicating whether the task
is up-to-date:

.. code-block:: python

    async def check_deps_uptodate(ctxt: UpToDateCtxt) -> bool:
        """
        Custom up-to-date check that verifies external dependencies.
        
        Returns True if task is up-to-date, False if it needs to run.
        """
        import os
        
        # Check if a specific file has been modified since last run
        dep_file = os.path.join(ctxt.rundir, "external_dep.txt")
        
        if not os.path.exists(dep_file):
            return False
        
        # Compare timestamps, checksums, etc.
        # ...
        
        return True

See :doc:`pytask_api` for complete documentation of the ``UpToDateCtxt`` class.

Task Output
===========

When a task is determined to be up-to-date, it is marked as such in the 
output:

.. code-block:: text

    << [1] Task mypackage.compile (up-to-date) 0.05ms

The previous output data is loaded from the task's ``exec.json`` file,
allowing downstream tasks to use cached results without re-executing.


The Memento System
==================

DV Flow Manager uses a memento pattern to store task execution state for
incremental builds. Each task can save arbitrary data that describes its
execution, which is used to determine if re-execution is needed.

How Mementos Work
-----------------

When a task executes:

1. Task runs and produces outputs
2. Task optionally creates a memento (dictionary of state data)
3. Memento is saved to the task's exec.json file
4. On next run, memento is passed to up-to-date check

Mementos typically store:

* File timestamps
* Content hashes
* Configuration values
* Dependency versions
* Any data needed to detect changes

Creating Mementos
-----------------

Task implementations return mementos in the TaskDataResult:

.. code-block:: python

    async def MyTask(ctxt, input) -> TaskDataResult:
        # Perform work
        result_file = os.path.join(ctxt.rundir, "output.txt")
        with open(result_file, "w") as f:
            f.write("result data")
        
        # Create memento with file timestamp
        memento = {
            "result_file": result_file,
            "timestamp": os.path.getmtime(result_file),
            "parameters": {
                "param1": input.params.param1
            }
        }
        
        return TaskDataResult(
            changed=True,
            memento=memento
        )

On the next run, this memento is available in ``input.memento`` for
comparison with current state.

Accessing Mementos
------------------

In up-to-date checks:

.. code-block:: python

    async def CheckUpToDate(ctxt: UpToDateCtxt) -> bool:
        if ctxt.memento is None:
            return False  # No previous execution
        
        # Access saved memento data
        prev_timestamp = ctxt.memento.get("timestamp")
        prev_params = ctxt.memento.get("parameters", {})
        
        # Compare with current state
        current_timestamp = os.path.getmtime(ctxt.memento["result_file"])
        current_params = {"param1": ctxt.params.param1}
        
        # Up-to-date if nothing changed
        return (prev_timestamp == current_timestamp and
                prev_params == current_params)

Memento Best Practices
----------------------

**Keep mementos small**: Only store data needed for change detection

**Use structured data**: Store dictionaries and lists that serialize to JSON

**Include version info**: Store schema versions if memento format might change

**Handle missing data**: Check for None and missing keys gracefully

**Be deterministic**: Ensure memento generation is consistent

Exec.json Structure
===================

Each task's execution data is stored in a JSON file with the following
structure:

.. code-block:: json

    {
      "name": "my_pkg.my_task",
      "status": 0,
      "changed": true,
      "params": {
        "param1": "value1",
        "param2": 42
      },
      "inputs": [
        {
          "type": "std.FileSet",
          "filetype": "verilogSource",
          "files": ["file1.v", "file2.v"]
        }
      ],
      "outputs": [
        {
          "type": "std.FileSet",
          "filetype": "simImage",
          "files": ["sim_image.so"]
        }
      ],
      "memento": {
        "timestamp": 1703456789.123,
        "checksum": "abc123def456"
      },
      "markers": [
        {
          "severity": "warning",
          "message": "Unused signal detected",
          "location": {
            "file": "src/module.v",
            "line": 42,
            "column": 10
          }
        }
      ],
      "exec_info": [
        {
          "cmd": ["verilator", "-c", "file.v"],
          "status": 0
        }
      ],
      "start_time": "2024-12-24T10:30:00Z",
      "end_time": "2024-12-24T10:30:05Z",
      "duration_ms": 5432
    }

Fields
------

* **name**: Fully-qualified task name
* **status**: Exit status (0 = success, non-zero = failure)
* **changed**: Whether the task's output changed from previous execution
* **params**: Task parameters used for this execution
* **inputs**: List of input data items received from dependencies
* **outputs**: List of output data items produced
* **memento**: Custom state data for incremental builds
* **markers**: Warnings, errors, and info messages
* **exec_info**: Commands executed and their results
* **start_time, end_time, duration_ms**: Timing information

Using Exec Data
---------------

Exec data files can be used for:

* **Debugging**: Inspect what inputs a task received
* **Analysis**: Review parameters and execution time
* **Documentation**: Generate reports on build process
* **Testing**: Verify task behavior and outputs

Example: Reading exec data:

.. code-block:: python

    import json
    
    with open("rundir/my_task/my_task.exec_data.json") as f:
        data = json.load(f)
    
    print(f"Task took {data['duration_ms']}ms")
    print(f"Executed {len(data['exec_info'])} commands")
    
    for marker in data['markers']:
        print(f"{marker['severity']}: {marker['message']}")

Advanced Incremental Build Patterns
====================================

Content-Based Detection
-----------------------

Instead of timestamps, use content hashes for more reliable detection:

.. code-block:: python

    import hashlib
    
    async def ComputeHash(filepath):
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    async def MyTask(ctxt, input):
        # Process files
        output_file = os.path.join(ctxt.rundir, "output.dat")
        # ... create output ...
        
        # Store content hash
        file_hash = await ComputeHash(output_file)
        
        return TaskDataResult(
            memento={"output_hash": file_hash}
        )

Dependency Tracking
-------------------

Track external dependencies explicitly:

.. code-block:: python

    async def TrackDependencies(ctxt: UpToDateCtxt) -> bool:
        # Read dependency file
        dep_file = os.path.join(ctxt.srcdir, "dependencies.txt")
        if not os.path.exists(dep_file):
            return False
        
        with open(dep_file) as f:
            current_deps = f.read().splitlines()
        
        # Compare with saved dependencies
        saved_deps = ctxt.memento.get("dependencies", [])
        
        # Check if list changed
        if set(current_deps) != set(saved_deps):
            return False
        
        # Check if any dependency file changed
        for dep in current_deps:
            if not os.path.exists(dep):
                return False
            current_time = os.path.getmtime(dep)
            saved_time = ctxt.memento.get(f"dep_time_{dep}")
            if saved_time is None or current_time != saved_time:
                return False
        
        return True

Multi-Stage Checking
--------------------

Combine multiple checks for accuracy:

.. code-block:: python

    async def ComplexUpToDate(ctxt: UpToDateCtxt) -> bool:
        # Quick check: parameters changed?
        if ctxt.memento.get("params") != ctxt.params.model_dump():
            return False
        
        # Medium check: timestamps changed?
        for file in ctxt.memento.get("files", []):
            if os.path.getmtime(file) != ctxt.memento.get(f"time_{file}"):
                return False
        
        # Expensive check: content hashes changed?
        for file in ctxt.memento.get("critical_files", []):
            current_hash = await ComputeHash(file)
            if current_hash != ctxt.memento.get(f"hash_{file}"):
                return False
        
        return True
