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

# Visualization
dfm graph task -o flow.dot  # Generate dependency graph
```

### Expression Syntax

Use `${{ }}` for dynamic parameter evaluation:

```yaml
msg: "Building version ${{ version }}"
iff: ${{ debug_level > 0 }}
command: ${{ "make debug" if debug else "make release" }}
```

## Detailed Documentation

For comprehensive documentation, see the following reference files:

- [Core Concepts](references/concepts.md) - Tasks, packages, dataflow, types
- [Task Reference](references/tasks.md) - Using and defining tasks
- [Standard Library](references/stdlib.md) - Built-in std.* tasks
- [CLI Reference](references/cli.md) - Command line interface
- [Advanced Patterns](references/advanced.md) - Complex workflows and optimization

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
