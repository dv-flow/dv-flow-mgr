# DV Flow Manager Task Reference

## Task Definition

### Basic Task

```yaml
- name: my_task
  uses: std.Message
  with:
    msg: "Hello World"
```

### Full Task Structure

```yaml
- name: task_name
  uses: base.Task
  scope: root                  # Visibility scope
  needs: [dep1, dep2]
  feeds: [consumer1]
  with:
    param1: value1
    param2:
      type: int
      value: 10
  iff: ${{ condition }}
  consumes: all
  passthrough: unused
  rundir: unique
  override: original_task
  body:
    - name: subtask
      uses: other.Task
```

## Task Visibility

Control task visibility using the `scope` field or inline scope markers.

### Visibility Scopes

| Scope | Description |
|-------|-------------|
| `root` | Entry point - shown in `dfm run` task listing |
| `export` | Visible outside package - can be in other package's `needs` |
| `local` | Only visible within its declaration fragment |
| (none) | Package-visible only (default) |

### Specifying Scope

**Using scope field:**

```yaml
- name: build
  scope: root
  run: make build

- name: main
  scope: [root, export]    # Multiple scopes
  run: ./main.sh
```

**Using inline markers (alternative to name:):**

```yaml
- root: build              # Equivalent to name: build + scope: root
  run: make build

- export: format           # Equivalent to name: format + scope: export
  run: format.sh

- local: helper            # Equivalent to name: helper + scope: local
  run: echo "internal"
```

### Visibility Best Practices

**Mark entry points as root:**
```yaml
- root: build
  desc: "Build project"
- root: test
  desc: "Run tests"
```

**Mark public APIs as export:**
```yaml
- export: compile
  desc: "Library compile function"
```

**Use local for helpers in compound tasks:**
```yaml
- name: process
  body:
  - local: step1
    run: ./step1.sh
  - name: result
    needs: [step1]
```

**Combine root+export for public entry points:**
```yaml
- name: main
  scope: [root, export]
  desc: "Main public entry point"
```

## Specifying Task Base

Use `uses` (or `type`) to specify the base task:

```yaml
- name: my_message
  uses: std.Message       # Full qualified name
  with:
    msg: "Hello"

- name: my_sim
  uses: hdlsim.vlt.SimImage
```

Common base tasks:
- `std.FileSet` - Collect files
- `std.Message` - Display message
- `std.Exec` - Run shell command
- `std.CreateFile` - Create file from content
- `std.SetEnv` - Set environment variables
- `hdlsim.vlt.SimImage` - Verilator simulation image
- `hdlsim.vlt.SimRun` - Run Verilator simulation

## Dependencies

### needs

Specify tasks that must complete before this task:

```yaml
- name: sources
  uses: std.FileSet
  with:
    include: "*.sv"

- name: compile
  uses: hdlsim.vlt.SimImage
  needs: [sources]

- name: run
  uses: hdlsim.vlt.SimRun
  needs: [compile]
```

Multiple dependencies:

```yaml
- name: link
  uses: my.Linker
  needs: [lib1, lib2, lib3]
```

### feeds

Inverse of `needs` - declare from producer's perspective:

```yaml
- name: sources
  uses: std.FileSet
  feeds: [compile]        # Equivalent to compile.needs: [sources]
```

## Parameter Overrides

### Simple Values

```yaml
- name: task1
  uses: std.Message
  with:
    msg: "Hello"
    count: 5
    enabled: true
    items: [a, b, c]
```

### Typed Parameters

```yaml
- name: task1
  uses: base.Task
  with:
    debug:
      type: bool
      value: false
    level:
      type: int
      value: 2
    name:
      type: str
      value: "default"
```

### Expression Values

```yaml
- name: task1
  uses: std.Message
  with:
    msg: "Building version ${{ version }}"
    opt_level: ${{ 3 if release else 0 }}
```

## Conditional Execution

Use `iff` for conditional task execution:

```yaml
- name: debug_task
  uses: std.Message
  iff: ${{ debug }}
  with:
    msg: "Debug mode enabled"

- name: coverage_task
  uses: coverage.Collect
  iff: ${{ enable_coverage and not quick_run }}
```

Common patterns:

```yaml
iff: ${{ flag }}                    # Boolean parameter
iff: ${{ level > 0 }}               # Comparison
iff: ${{ mode == "debug" }}         # String comparison
iff: ${{ a and b }}                 # Logical AND
iff: ${{ a or b }}                  # Logical OR
iff: ${{ not disabled }}            # Negation
```

## Dataflow Control

### consumes

Control what input data reaches the task implementation:

```yaml
# Consume all inputs (default for implementation tasks)
consumes: all

# Consume no inputs (default for DataItem tasks)
consumes: none

# Selective consumption by pattern
consumes:
  - type: std.FileSet
    filetype: systemVerilogSource
  - type: hdlsim.SimElabArgs
```

### passthrough

Control what inputs forward to output:

```yaml
# Pass all inputs
passthrough: all

# Pass no inputs
passthrough: none

# Pass only unconsumed inputs (default)
passthrough: unused

# Selective passthrough by pattern
passthrough:
  - type: std.FileSet
    filetype: verilogSource
```

### Pattern Matching

Match data items by field values:

```yaml
consumes:
  - type: std.FileSet           # Match by type
  - filetype: systemVerilogSource  # Match by field
  - type: std.FileSet
    filetype: verilogSource
    attributes: [rtl]           # Multiple field match (AND)
```

## Compound Tasks

Define tasks with subtasks:

```yaml
- name: build_flow
  body:
    - name: gather
      uses: std.FileSet
      with:
        include: "*.sv"
    
    - name: compile
      uses: hdlsim.vlt.SimImage
      needs: [gather]
    
    - name: run
      uses: hdlsim.vlt.SimRun
      needs: [compile]
```

### Shared Run Directory

Use `rundir: inherit` for subtasks to share directory:

```yaml
- name: create_and_process
  rundir: inherit
  body:
    - name: create
      uses: std.CreateFile
      with:
        filename: data.txt
        content: "test data"
    
    - name: process
      uses: std.Exec
      needs: [create]
      with:
        command: "cat data.txt"
```

### Parameterized Compound Tasks

```yaml
- name: configurable_build
  with:
    debug:
      type: bool
      value: false
  body:
    - name: options
      uses: hdlsim.SimElabArgs
      iff: ${{ debug }}
      with:
        args: [--trace-fst]
    
    - name: build
      uses: hdlsim.vlt.SimImage
      needs: [options]
```

## Task Override

Replace existing task implementations:

```yaml
# Original task
- name: sim
  uses: hdlsim.vlt.SimImage
  with:
    optimization: "O2"

# Override for debug configuration
- name: sim_debug
  override: sim
  with:
    optimization: "O0"
    debug: true
```

Override in configurations:

```yaml
configs:
  - name: fast
    tasks:
      - name: sim_fast
        override: sim
        with:
          optimization: "O0"
```

## DataItem Tasks

Use a type as base to produce data without implementation:

```yaml
types:
  - name: CompilerFlags
    with:
      flags:
        type: list
        value: []

tasks:
  - name: debug_flags
    uses: CompilerFlags
    with:
      flags: ["-g", "-O0"]
  
  - name: compile
    uses: my.Compiler
    needs: [debug_flags]
```

## Run Directory Modes

### unique (default)

Each task gets dedicated directory:

```yaml
- name: task1
  uses: std.Exec
  rundir: unique    # Gets own directory: rundir/task1/
```

### inherit

Share parent's directory:

```yaml
- name: parent
  rundir: inherit   # All subtasks share directory
  body:
    - name: step1
      uses: std.CreateFile
    - name: step2
      uses: std.Exec
      needs: [step1]  # Can access step1's files
```

## Matrix Strategy

Generate multiple task instances:

```yaml
- name: test_suite
  strategy:
    matrix:
      test: [test1, test2, test3]
      seed: [100, 200]
  body:
    - name: run
      uses: hdlsim.vlt.SimRun
      with:
        plusargs:
          - "+test=${{ matrix.test }}"
          - "+seed=${{ matrix.seed }}"
```

This generates 6 tasks (3 tests × 2 seeds).

## Generator Strategy

Programmatic task generation:

```yaml
- name: dynamic_tests
  strategy:
    generate:
      run: my_pkg.generators.CreateTests
```

Python generator:

```python
def CreateTests(ctxt, input):
    for i in range(10):
        task = ctxt.mkTaskNode(
            "hdlsim.vlt.SimRun",
            name=ctxt.mkName(f"test_{i}"),
            plusargs=[f"+seed={i}"]
        )
        ctxt.addTask(task)
```

## Common Task Patterns

### File Collection and Compilation

```yaml
tasks:
  - name: rtl
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: src/rtl
      include: "*.sv"
  
  - name: tb
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: src/tb
      include: "*.sv"
  
  - name: sim
    uses: hdlsim.vlt.SimImage
    needs: [rtl, tb]
    with:
      top: [tb_top]
```

### Conditional Options

```yaml
tasks:
  - name: base_options
    uses: hdlsim.SimElabArgs
    body:
      - name: trace
        uses: hdlsim.SimElabArgs
        iff: ${{ enable_trace }}
        with:
          args: [--trace-fst]
      
      - name: coverage
        uses: hdlsim.SimElabArgs
        iff: ${{ enable_coverage }}
        with:
          args: [--coverage]
```

### Environment Setup

```yaml
tasks:
  - name: setup_env
    uses: std.SetEnv
    with:
      setenv:
        TOOL_HOME: /opt/tools
      append_path:
        PATH: /opt/tools/bin
  
  - name: run_tool
    uses: std.Exec
    needs: [setup_env]
    with:
      command: "my_tool --run"
```
