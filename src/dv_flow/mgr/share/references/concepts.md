# DV Flow Manager Core Concepts

## Tasks

Tasks are the fundamental unit of behavior in DV Flow Manager. A task:
- Accepts data from tasks it depends on
- Performs work (compilation, execution, file generation, etc.)
- Produces output data for dependent tasks

### Task Structure

```yaml
- name: my_task
  uses: base.Task           # Inherit from existing task
  needs: [dep1, dep2]       # Dependencies
  with:                     # Parameter overrides
    param1: value1
  iff: ${{ condition }}     # Conditional execution
  consumes: all             # Input filtering
  passthrough: unused       # Output forwarding
  rundir: unique            # Directory mode
```

### Task Fields

| Field | Description |
|-------|-------------|
| `name` | Unique task identifier within package |
| `uses` | Base task to inherit from (e.g., `std.FileSet`) |
| `type` | Alias for `uses` |
| `scope` | Visibility: `root`, `export`, `local`, or list |
| `needs` | List of task dependencies |
| `feeds` | Inverse of `needs` - declares what depends on this task |
| `with` | Parameter values to override |
| `iff` | Condition expression for conditional execution |
| `consumes` | Controls what input data reaches implementation |
| `passthrough` | Controls what inputs forward to output |
| `rundir` | Directory mode: `unique` (default) or `inherit` |
| `override` | Name of task to replace |
| `body` | List of subtasks (compound tasks) |

### Task Visibility

Tasks can control their visibility using `scope`:

| Scope | Description |
|-------|-------------|
| `root` | Entry point - shown in `dfm run` task listing |
| `export` | Visible outside package - can be referenced in other packages' `needs` |
| `local` | Only visible within its declaration fragment |
| (none) | Package-visible only (default) |

Specify scope via field or inline markers:

```yaml
# Using scope field
- name: build
  scope: root
  run: make build

# Using inline marker (equivalent to name + scope)
- root: build
  run: make build

# Multiple scopes
- name: main
  scope: [root, export]
  run: ./main.sh
```

### Task Types

1. **Derived Tasks**: Inherit from existing tasks, override parameters
2. **Compound Tasks**: Contain subtasks in `body`
3. **DataItem Tasks**: Use a type as base to produce data without implementation
4. **Python Tasks**: Custom implementation via `pytask`

## Packages

Packages are parameterized namespaces that organize tasks and types.

### Package Structure

```yaml
package:
  name: my_package
  
  with:                    # Package parameters
    debug:
      type: bool
      value: false
  
  imports:                 # Import other packages
    - path/to/other
    - name: hdlsim.vlt
      as: sim
  
  types:                   # Custom types
    - name: MyOptions
      with:
        option1:
          type: str
          value: "default"
  
  tasks:                   # Task definitions
    - name: task1
      uses: std.Message
  
  configs:                 # Named configurations
    - name: debug
      with:
        debug:
          value: true
  
  fragments:               # Split package across files
    - src/rtl/flow.yaml
    - src/tb/flow.yaml
```

### Package Parameters

```yaml
with:
  param_name:
    type: str|int|bool|list|map
    value: default_value
    doc: "Optional documentation"
```

Supported types: `str`, `int`, `bool`, `list`, `map`

### Package Imports

```yaml
imports:
  - relative/path/to/package    # By path
  - name: package.name          # By name
    as: alias                   # Optional alias
    with:                       # Parameter overrides
      param: value
```

### Package Configurations

```yaml
configs:
  - name: debug
    uses: base_config           # Inherit from another config
    with:                       # Parameter overrides
      debug:
        value: true
    tasks:                      # Additional/override tasks
      - name: debug_task
        override: original_task
    extensions:                 # Task extensions
      - task: some.Task
        with:
          extra_param: value
```

Select configuration: `dfm run task -c debug`

## Dataflow

Tasks communicate via typed data items, not global variables.

### Dependency Declaration

```yaml
- name: producer
  uses: std.FileSet
  with:
    include: "*.sv"

- name: consumer
  uses: hdlsim.vlt.SimImage
  needs: [producer]         # Receives data from producer
```

### Input/Output Control

**consumes** - What input data reaches the task implementation:
- `all` - All inputs (default for tasks with implementation)
- `none` - No inputs (default for DataItem tasks)
- Pattern list - Selective filtering

**passthrough** - What inputs forward to output:
- `all` - All inputs
- `none` - No inputs
- `unused` - Inputs not consumed (default)
- Pattern list - Selective filtering

```yaml
- name: selective
  uses: hdlsim.vlt.SimImage
  needs: [sources, options]
  consumes:
    - type: std.FileSet
      filetype: systemVerilogSource
  passthrough:
    - type: hdlsim.SimElabArgs
```

### Pattern Matching

Patterns match data items by field values:

```yaml
consumes:
  - type: std.FileSet           # Match type
    filetype: verilogSource     # Match filetype field
    attributes: [uvm]           # Match attributes
```

## Types

Custom data structures for task parameters.

```yaml
types:
  - name: MyOptions
    with:
      flag1:
        type: bool
        value: false
      value1:
        type: str
        value: "default"

  - name: ExtendedOptions
    uses: MyOptions             # Inherit from MyOptions
    with:
      flag2:
        type: bool
        value: true
```

Use types as task base to produce data items:

```yaml
- name: my_options
  uses: MyOptions
  with:
    flag1: true
```

## Expressions

Dynamic parameter evaluation using `${{ }}` syntax.

### Basic Usage

```yaml
msg: "Version ${{ version }}"
iff: ${{ debug }}
value: ${{ base_value * 2 }}
```

### Operators

- Arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Logical: `and`, `or`, `not`
- Conditional: `x if condition else y`

### Built-in Functions

- `len(x)` - Length of list/string
- `str(x)` - Convert to string
- `int(x)` - Convert to integer
- `bool(x)` - Convert to boolean

### Expression Contexts

- Package parameters: `${{ package_param }}`
- Task parameters: `${{ task_param }}`
- Parent task parameters (in compound tasks)
- Matrix variables: `${{ matrix.var }}`

## Run Directory Modes

Control where tasks execute:

- `unique` (default) - Dedicated directory for each task
- `inherit` - Share parent task's directory

```yaml
- name: compound_task
  rundir: inherit           # All subtasks share directory
  body:
    - name: create_file
      uses: std.CreateFile
    - name: process_file
      shell: bash
      run: cat data.txt
      needs: [create_file]  # Can access create_file's output
```

## Compound Tasks

Tasks containing subtasks:

```yaml
- name: build_and_test
  body:
    - name: build
      uses: hdlsim.vlt.SimImage
      needs: [sources]
    
    - name: test
      uses: hdlsim.vlt.SimRun
      needs: [build]
```

Compound task output is the union of all subtask outputs (respecting passthrough settings).

## Conditional Execution

Execute tasks conditionally using `iff`:

```yaml
- name: debug_options
  uses: hdlsim.SimElabArgs
  iff: ${{ debug_level > 0 }}
  with:
    args: [--trace-fst]
```

## Task Override

Replace task implementations:

```yaml
- name: fast_sim
  override: sim             # Replaces 'sim' task
  uses: hdlsim.vlt.SimImage
  with:
    optimization: "O0"
```

## Package Fragments

Split large packages across multiple files using fragments. The root
file uses `package:` while child files use `fragment:`.

```yaml
# Top-level flow.dv
package:
  name: my_project
  fragments:
    - src/rtl/flow.dv
    - tb/flow.dv

# src/rtl/flow.dv
fragment:
  tasks:
    - name: rtl_sources
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"

# tb/flow.dv -- intermediate fragment with nesting
fragment:
  fragments:
    - tests/flow.dv
    - testbench/flow.dv
  tasks:
    - name: tb_sources
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
```

All fragments contribute to the same package namespace. Task names must be
unique across all fragments.

Fragment paths are relative to the file containing the `fragments:` list.

### Fragment Allowed Fields

| Field | Allowed? | Notes |
|-------|----------|-------|
| tasks | Yes | Same syntax as package tasks |
| types | Yes | Data type definitions |
| configs | Yes | Configuration definitions |
| imports | Yes | Package imports |
| filters | Yes | Filter definitions |
| fragments | Yes | Nested fragment paths |
| name | Yes | Optional; prefixes task names |
| with | **No** | Package-level params only in root |
| desc | **No** | Package description only in root |

### Dependency Graph Best Practices

Each task should declare only its **direct** dependencies in `needs`.
DFM resolves transitive dependencies automatically.

**Co-location principle:** Define tasks in the same `flow.dv` as the source
files they describe. Use fragments to link directories together. The
top-level build task should list only its direct inputs.

```yaml
# BAD: flat needs list
- root: build
  uses: sim.SimImage
  needs: [rtl, pkg_a_hdl, pkg_a_hvl, pkg_b_hdl, pkg_b_hvl,
          env, sequences, tests, hdl_top, hvl_top]

# GOOD: each task declares only direct deps
# verification_ip/pkg_a/flow.dv
- name: pkg_a_hvl
  needs: [pkg_a_hdl]  # direct dep only

# tb/flow.dv
- root: build
  uses: sim.SimImage
  needs: [hdl_top, hvl_top, rtl]
```

Use `dfm graph <task> -o flow.dot` to visualize and verify the DAG.
