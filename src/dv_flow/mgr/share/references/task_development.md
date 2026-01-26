---
name: dv-flow-task-development
description: Develop custom task implementations and plugin packages for DV Flow Manager. Use when creating new pytask functions, PyTask classes, or DFM plugin packages.
---

# Developing New Task Implementations

This document covers how to create custom task implementations and packages for DV Flow Manager.

**When to use this skill:**
- Creating new pytask functions or classes
- Building plugin packages for DFM
- Implementing custom dataflow patterns
- Setting up incremental execution with mementos

## Task Implementation Approaches

DV Flow provides several ways to implement tasks:

1. **Inline pytask** - Simple Python code embedded in YAML
2. **External pytask function** - Async Python function in a module
3. **PyTask class** - Dataclass-based implementation for complex tasks
4. **PyPkg package factory** - Define entire packages in Python

## Minimal Task Implementation

### Function-Based (Simplest)

```python
# my_package/tasks.py
from dv_flow.mgr import TaskDataResult

async def MyTask(runner, input) -> TaskDataResult:
    """Simple task implementation."""
    print(f"Running: {input.name}")
    print(f"Params: {input.params.my_param}")
    
    # Return success with no output
    return TaskDataResult(status=0, changed=True)
```

```yaml
# flow.yaml
package:
  name: my_package
  
  tasks:
  - name: my_task
    shell: pytask
    run: my_package.tasks.MyTask
    with:
      my_param:
        type: str
        value: "default"
```

### Inline pytask (Quick Prototyping)

```yaml
package:
  name: quick_tasks
  
  tasks:
  - name: inline_task
    shell: pytask
    run: |
      print(f"Message: {input.params.msg}")
      return TaskDataResult(status=0, changed=True)
    with:
      msg:
        type: str
        value: ""
```

## Task Implementation API

### Input Data Structure

Every task implementation receives:

```python
async def MyTask(runner, input) -> TaskDataResult:
    # input.name      - Task name (str)
    # input.rundir    - Task's run directory (str)
    # input.srcdir    - Source directory (str) 
    # input.params    - Task parameters (object)
    # input.inputs    - List of input data items from dependencies
    # input.changed   - Whether upstream changed (bool)
    # input.memento   - Previous execution data (dict or None)
```

### TaskDataResult Return Value

```python
from dv_flow.mgr import TaskDataResult, TaskMarker, FileSet

return TaskDataResult(
    status=0,              # 0=success, non-zero=failure
    changed=True,          # Did outputs change?
    output=[               # List of output data items
        FileSet(
            src=input.name,
            filetype="verilogSource",
            basedir=input.rundir,
            files=["output.v"]
        )
    ],
    markers=[              # Diagnostics for user
        TaskMarker(msg="Warning: deprecated", severity="warning")
    ],
    memento={"key": "value"}  # State for incremental builds
)
```

### Executing Subprocesses

Use `runner.exec()` for subprocess execution with logging:

```python
async def CompileTask(runner, input) -> TaskDataResult:
    cmd = ["gcc", "-c", "file.c", "-o", "file.o"]
    
    status = await runner.exec(
        cmd,
        logfile="compile.log",    # Log stdout/stderr
        cwd=input.rundir          # Working directory
    )
    
    return TaskDataResult(status=status, changed=(status == 0))
```

### Executing Multiple Commands in Parallel

Use `runner.exec_parallel()` to execute multiple commands concurrently, 
respecting the configured nproc limits:

```python
from dv_flow.mgr import ExecCmd

async def ParallelCompileTask(runner, input) -> TaskDataResult:
    # Define commands to run in parallel
    cmds = [
        ExecCmd(cmd=["gcc", "-c", "file1.c", "-o", "file1.o"], logfile="compile1.log"),
        ExecCmd(cmd=["gcc", "-c", "file2.c", "-o", "file2.o"], logfile="compile2.log"),
        ExecCmd(cmd=["gcc", "-c", "file3.c", "-o", "file3.o"], logfile="compile3.log"),
    ]
    
    # Execute all commands in parallel (subject to nproc limits)
    statuses = await runner.exec_parallel(cmds)
    
    # statuses is a list of exit codes in the same order as cmds
    failed = any(s != 0 for s in statuses)
    
    return TaskDataResult(status=1 if failed else 0, changed=True)
```

The `ExecCmd` class describes each command:
- `cmd`: List of command arguments
- `logfile`: Optional log file name for output
- `cwd`: Optional working directory (defaults to task rundir)
- `env`: Optional environment variables dict

### Processing Input Filesets

```python
async def ProcessFiles(runner, input) -> TaskDataResult:
    files = []
    incdirs = []
    
    for item in input.inputs:
        if item.type == "std.FileSet":
            if item.filetype in ("verilogSource", "systemVerilogSource"):
                for f in item.files:
                    files.append(os.path.join(item.basedir, f))
                incdirs.extend(item.incdirs)
    
    # Use files and incdirs...
```

## PyTask Class-Based Implementation

For complex tasks, use the `PyTask` dataclass pattern:

```python
# my_package/compiler.py
from dv_flow.mgr import PyTask, TaskDataResult, FileSet
import dataclasses as dc
import os

@dc.dataclass
class Compile(PyTask):
    desc = "Compile HDL sources"
    doc = """
    Compiles Verilog/SystemVerilog sources.
    Supports multiple file types and optimization levels.
    """
    
    @dc.dataclass
    class Params:
        sources: list = dc.field(default_factory=list)
        optimization: str = "O2"
        debug: bool = False
        top: str = ""
    
    async def __call__(self):
        # Access parameters via self.params
        # Access context via self._ctxt
        # Access input via self._input
        
        cmd = ["verilator", "--binary", "-o", "simv"]
        
        if self.params.debug:
            cmd.append("-g")
        cmd.append(f"-{self.params.optimization}")
        
        if self.params.top:
            cmd.extend(["--top-module", self.params.top])
        
        # Gather source files from inputs
        for item in self._input.inputs:
            if item.type == "std.FileSet":
                for f in item.files:
                    cmd.append(os.path.join(item.basedir, f))
        
        status = await self._ctxt.exec(cmd, logfile="build.log")
        
        output = []
        if status == 0:
            output.append(FileSet(
                src=self._input.name,
                filetype="simDir",
                basedir=self._input.rundir
            ))
        
        return TaskDataResult(status=status, changed=True, output=output)
```

Reference in YAML:
```yaml
tasks:
- name: compile
  shell: pytask
  run: my_package.compiler.Compile
  with:
    top: [my_top]
    debug: true
```

## Creating a Plugin Package

### Package Structure

```
my-dv-flow-plugin/
├── pyproject.toml
├── src/
│   └── my_flow_plugin/
│       ├── __init__.py
│       ├── __ext__.py          # Plugin entry point
│       ├── flow.yaml             # Package definition
│       └── tasks.py            # Task implementations
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "my-dv-flow-plugin"
version = "1.0.0"
dependencies = ["dv-flow-mgr"]

# Register plugin with dv-flow-mgr
[project.entry-points."dv_flow.mgr"]
my_plugin = "my_flow_plugin.__ext__"

[tool.setuptools.package-data]
"my_flow_plugin" = ["*.dv"]
```

### __ext__.py (Plugin Entry Point)

```python
import os

def dvfm_packages():
    """Return mapping of package names to flow.yaml paths."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    return {
        'my_tool': os.path.join(pkg_dir, "flow.yaml"),
        # Can register multiple packages
        'my_tool.extra': os.path.join(pkg_dir, "extra_flow.yaml"),
    }
```

### flow.yaml (Package Definition)

```yaml
package:
  name: my_tool
  
  # Define abstract base tasks
  tasks:
  - name: Compile
    consumes:
    - filetype: verilogSource
    - filetype: systemVerilogSource
    with:
      optimization:
        type: str
        value: "O2"
      debug:
        type: bool
        value: false
  
  - name: Run
    consumes:
    - filetype: simDir
    with:
      args:
        type: list
      plusargs:
        type: list
  
  # Define custom types
  types:
  - name: CompileArgs
    with:
      args:
        type: list
      defines:
        type: list
```

### Concrete Implementation Package

```yaml
# vlt_flow.yaml - Verilator-specific implementation
package:
  name: my_tool.vlt
  
  tasks:
  - name: Compile
    uses: my_tool.Compile
    pytask: my_flow_plugin.vlt_tasks.Compile
  
  - name: Run
    uses: my_tool.Run
    pytask: my_flow_plugin.vlt_tasks.Run
```

## Dataflow Patterns

### Defining What a Task Consumes

```yaml
tasks:
- name: simulator
  # Only receive these input types
  consumes:
  - filetype: verilogSource
  - filetype: systemVerilogSource
  - type: hdlsim.SimCompileArgs
  with:
    top:
      type: list
```

### Defining What a Task Produces

Tasks produce output via `TaskDataResult.output`:

```python
from dv_flow.mgr import FileSet

return TaskDataResult(
    output=[
        FileSet(
            src=input.name,
            filetype="simLib",
            basedir=input.rundir,
            files=["work/_lib.so"]
        )
    ]
)
```

### Passthrough Behavior

```yaml
tasks:
- name: preprocess
  passthrough: all      # Forward all inputs to dependents
  
- name: filter
  passthrough: none     # Don't forward any inputs
  
- name: selective
  passthrough: unused   # Forward only unconsumed inputs (default)
```

## Incremental Execution

### Using Mementos

Store state between executions for incremental builds:

```python
from pydantic import BaseModel

class MyMemento(BaseModel):
    input_hash: str
    timestamp: float

async def MyTask(runner, input) -> TaskDataResult:
    # Load previous memento
    prev = MyMemento(**input.memento) if input.memento else None
    
    # Calculate current state
    current_hash = compute_hash(input.params)
    
    if prev and prev.input_hash == current_hash:
        # Nothing changed, skip execution
        return TaskDataResult(status=0, changed=False, memento=prev)
    
    # Execute task...
    
    # Save new memento
    new_memento = MyMemento(input_hash=current_hash, timestamp=time.time())
    return TaskDataResult(status=0, changed=True, memento=new_memento)
```

### Custom Up-to-Date Check

```yaml
tasks:
- name: generate
  uptodate: my_package.checks.check_inputs
  run: my_package.tasks.generate
```

```python
# my_package/checks.py
async def check_inputs(ctxt) -> bool:
    """Return True if up-to-date, False to re-run."""
    import glob
    
    prev_files = ctxt.memento.get("files", []) if ctxt.memento else []
    current_files = glob.glob(os.path.join(ctxt.srcdir, "*.tmpl"))
    
    if set(prev_files) != set(current_files):
        return False
    
    for f in current_files:
        prev_mtime = ctxt.memento.get(f"mtime_{f}")
        if prev_mtime != os.path.getmtime(f):
            return False
    
    return True
```

## Task Graph Generation

For dynamic task creation:

```yaml
tasks:
- name: test_suite
  with:
    test_list:
      type: str
      value: "tests.json"
  strategy:
    generate:
      run: my_package.generators.create_tests
```

```python
# my_package/generators.py
import json
import os

def create_tests(ctxt, input):
    """Generate test tasks from JSON file."""
    test_file = os.path.join(ctxt.srcdir, input.params.test_list)
    
    with open(test_file) as f:
        tests = json.load(f)
    
    for test in tests:
        task = ctxt.mkTaskNode(
            "hdlsim.vlt.SimRun",
            name=ctxt.mkName(f"test_{test['name']}"),
            plusargs=[f"+test={test['name']}", f"+seed={test.get('seed', 0)}"]
        )
        ctxt.addTask(task)
```

## Best Practices

### Task Implementation Checklist

1. **Return proper status** - 0 for success, non-zero for failure
2. **Set changed flag** - False only when outputs are identical
3. **Use mementos** - For incremental execution
4. **Log output** - Use `runner.exec()` with `logfile=`
5. **Report errors** - Add `TaskMarker` for user-visible issues
6. **Document parameters** - Add `doc:` field in YAML

### Package Development Checklist

1. **Entry point** - Register via `pyproject.toml` entry-points
2. **Package data** - Include `.dv` files in package data
3. **Abstract base tasks** - Define interface in base package
4. **Concrete implementations** - Create tool-specific sub-packages
5. **Type definitions** - Define custom types for data exchange
6. **Documentation** - Include usage examples

### Debugging Tips

```bash
# View task details
dfm show task my_package.my_task

# Generate dependency graph
dfm graph my_task -o flow.dot

# Run single task with verbose output
dfm run my_task -j 1 -u log

# Check generated files in rundir/
ls rundir/my_task/
```
