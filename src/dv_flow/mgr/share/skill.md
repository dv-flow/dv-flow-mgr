---
name: dv-flow-manager
description: Create and modify DV Flow Manager (dfm) YAML-based build flows for silicon design and verification projects. Use when working with flow.yaml, flow.dv files, or dfm commands.
---

# DV Flow Manager (dfm)

DV Flow Manager is a YAML-based build system and execution engine designed for silicon design and verification projects. It orchestrates tasks through declarative workflows with dataflow-based dependency management.

## When to Use This Skill

Use this skill when:
- Creating or modifying `flow.yaml` or `flow.dv` files
- Writing task definitions for HDL compilation, simulation, or verification
- Configuring dataflow between tasks using `needs`, `consumes`, `passthrough`
- Setting up package parameters and configurations
- Running `dfm` commands (run, show, graph)
- Debugging build flow issues
- Working with standard library tasks (std.FileSet, std.Exec, std.Message, etc.)
- **Executing dfm commands from within an LLM-driven Prompt task**

## Quick Reference

### Minimal Flow Example

```yaml
package:
  name: my_project
  
  tasks:
    - name: rtl_files
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: sim
      uses: hdlsim.vlt.SimImage
      needs: [rtl_files]
      with:
        top: [my_top]
```

### Key Commands

```bash
# Run commands
dfm run [tasks...]          # Execute tasks
dfm run -j 4                # Run with 4 parallel jobs
dfm run --clean             # Clean rebuild
dfm run -c debug            # Use 'debug' configuration
dfm run -D param=value      # Override parameter

# Discovery commands (for humans and Agents)
dfm show packages           # List all available packages
dfm show packages --json    # JSON output for Agents
dfm show tasks              # List all visible tasks
dfm show tasks --search kw  # Search tasks by keyword
dfm show task std.FileSet   # Show detailed task info
dfm show types              # List data types and tags
dfm show project            # Show current project structure
dfm context --json          # Get full project context (for Agents)

# Visualization
dfm graph task -o flow.dot  # Generate dependency graph

# Validation
dfm validate                # Validate flow configuration
dfm validate --json         # JSON output for programmatic use
```

### Expression Syntax

Use `${{ }}` for dynamic parameter evaluation:

```yaml
msg: "Building version ${{ version }}"
iff: ${{ debug_level > 0 }}
command: ${{ "make debug" if debug else "make release" }}
```

## LLM Call Interface (Running Inside Prompt Tasks)

When running inside an LLM-driven `std.Prompt` task, the `dfm` command automatically
connects to the parent DFM session via a Unix socket. This enables LLMs to:

- Execute tasks that share resources with the parent session
- Query project state and task information
- Validate configurations before execution

### Environment Detection

When `DFM_SERVER_SOCKET` environment variable is set, `dfm` runs in client mode:

```bash
# These commands work inside a Prompt task:
dfm run task1 task2         # Execute tasks via parent session
dfm show tasks              # Query available tasks
dfm context --json          # Get project context
dfm validate                # Validate configuration
dfm ping                    # Health check
```

### Running Tasks from Within a Prompt

When an LLM needs to compile or simulate code it generated:

```bash
# 1. Create RTL files
cat > counter.sv << 'EOF'
module counter(input clk, rst_n, output logic [7:0] count);
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) count <= 0;
    else count <= count + 1;
endmodule
EOF

# 2. Run compilation via parent DFM session
dfm run hdlsim.vlt.SimImage -D hdlsim.vlt.SimImage.top=counter

# 3. Check result (JSON output)
# Returns: {"status": 0, "outputs": [...], "markers": []}
```

### Querying Project State

```bash
# Get full project context
dfm context --json
# Returns:
# {
#   "project": {"name": "my_project", "root_dir": "/path/to/project"},
#   "tasks": [{"name": "my_project.build", "scope": "root", ...}],
#   "types": [...],
#   "skills": [...]
# }

# Get specific task details
dfm show task my_project.build --json
# Returns detailed task information including parameters and dependencies
```

### Benefits of Server Mode

1. **Resource Sharing**: Respects parent session's parallelism limits (`-j`)
2. **State Consistency**: Sees outputs from tasks already completed
3. **Cache Sharing**: Uses same memento cache for incremental builds
4. **Unified Logging**: All task output appears in parent session's logs

## Detailed Documentation

For comprehensive documentation, see the following reference files:

- [Core Concepts](references/concepts.md) - Tasks, packages, dataflow, types
- [Task Reference](references/tasks.md) - Using and defining tasks
- [Standard Library](references/stdlib.md) - Built-in std.* tasks
- [CLI Reference](references/cli.md) - Command line interface
- [Advanced Patterns](references/advanced.md) - Complex workflows and optimization
- [Flow Schema](dv.flow.schema.json) - JSON Schema for flow.yaml validation

## Flow File Format

DV Flow uses YAML files (`flow.yaml` or `flow.dv`) to define workflows. The file structure is validated against a JSON Schema located at `dv.flow.schema.json`.

### Schema Validation

To validate your flow file or generate the schema:

```bash
# Get the JSON Schema
dfm util schema > flow.schema.json

# Use with YAML validators (e.g., VS Code YAML extension)
# Add to your flow.yaml:
# yaml-language-server: $schema=./dv.flow.schema.json
```

The schema defines two root types:
- **package** - Full project definition with tasks, types, configs, and imports
- **fragment** - Reusable partial definition for inclusion in packages

## Core Concepts Summary

### Tasks
Fundamental units of behavior. Tasks accept data from dependencies (`needs`) and produce outputs. Most tasks inherit from existing tasks using `uses`:

```yaml
- name: my_task
  uses: std.Message
  with:
    msg: "Hello!"
```

### Task Visibility
Control which tasks are entry points and which are API boundaries:

| Scope | Behavior |
|-------|----------|
| `root` | Entry point - shown in `dfm run` listing |
| `export` | Visible outside package for `needs` references |
| `local` | Only visible within its declaration fragment |
| (none) | Package-visible only (default) |

```yaml
# Entry point (shown in task listing)
- root: build
  desc: "Build project"
  run: make build

# Public API (other packages can use)
- export: compile
  run: ./compile.sh

# Both entry point AND public API
- name: main
  scope: [root, export]
  run: ./main.sh
```

**Best Practices:**
- Mark user-facing tasks as `root` so they appear in `dfm run` listing
- Mark tasks other packages should depend on as `export`
- Use `local` for helper tasks in compound task bodies
- Tasks without scope are only visible within the same package

### Packages
Parameterized namespaces that organize tasks. Defined in `flow.yaml` or `flow.dv`:

```yaml
package:
  name: my_package
  with:
    debug:
      type: bool
      value: false
  tasks:
    - name: task1
      uses: std.Message
```

### Dataflow
Tasks communicate via typed data items, not global variables:
- `needs: [task1, task2]` - Specify dependencies
- `consumes: all|none|[patterns]` - Control what inputs reach implementation
- `passthrough: all|none|unused|[patterns]` - Control what inputs forward to output

## File Structure

```
project/
├── flow.yaml           # Main package definition
├── rundir/             # Task execution workspace (created by dfm)
│   ├── cache/          # Task mementos and artifacts
│   └── log/            # Execution traces
└── packages/           # Optional sub-packages
```

## Installation

```bash
pip install dv-flow-mgr
pip install dv-flow-libhdlsim  # Optional: HDL simulator support
```

## Detailed Documentation

For comprehensive documentation, see the following reference files:

- [Core Concepts](references/concepts.md) - Tasks, packages, dataflow, types
- [Task Reference](references/tasks.md) - Using and defining tasks
- [Standard Library](references/stdlib.md) - Built-in std.* tasks
- [CLI Reference](references/cli.md) - Command line interface
- [Advanced Patterns](references/advanced.md) - Complex workflows and optimization
- [Task Development](references/task_development.md) - **Creating custom task implementations and plugin packages** (use when developing new tasks)
