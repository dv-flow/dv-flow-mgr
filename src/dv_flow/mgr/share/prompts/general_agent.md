# General AI Agent Prompt for DV Flow Manager

This document provides guidance for AI agents (LLMs) working with DV Flow 
Manager (dfm), a dataflow-based build system for silicon design and verification.

## Overview

DV Flow Manager (dfm) automates build and simulation workflows for hardware
design. It uses a declarative YAML/DV syntax to define tasks and their
dependencies.

## Discovery Workflow

Before making changes to a DFM project, gather context:

### Step 1: Get Skill Documentation
```bash
dfm --help
# Look for: "For LLM agents: See the skill file at: /path/to/skill.md"
# Read that file for comprehensive documentation
```

### Step 2: Get Project Context
```bash
dfm context --json
```
This returns:
- Project name and location
- Available tasks
- Available types
- Configurations
- Imports
- Available skills

### Step 3: Discover Package Capabilities
```bash
dfm show skills
dfm show skills <skill_name> --full
```

### Step 4: Validate Understanding
```bash
dfm validate --json
```

## Core Concepts

### Package Structure
```yaml
package:
  name: my_package
  
  imports:       # External package dependencies
  with:          # Package parameters
  configs:       # Named configuration sets
  types:         # Type definitions
  tasks:         # Task definitions
```

### Task Definition
```yaml
- name: task_name
  uses: base.Task          # Inherit from base task
  scope: root              # Make runnable (optional)
  needs: [dep1, dep2]      # Dependencies
  with:                    # Parameters
    param1: value1
```

### Common Task Types

| Task | Purpose | Package |
|------|---------|---------|
| `std.FileSet` | Collect source files | std |
| `std.Message` | Print a message | std |
| `sim.SimImage` | Compile simulation | hdlsim.* |
| `sim.SimRun` | Run simulation | hdlsim.* |
| `sim.SimLibUVM` | UVM library | hdlsim.* |

## CLI Reference

### Running Tasks
```bash
dfm run <task>              # Run a task
dfm run <task> -c <config>  # With configuration
dfm run <task> -D key=val   # With parameter override
```

### Discovery
```bash
dfm show packages           # List packages
dfm show tasks              # List tasks
dfm show task <name> --json # Task details
dfm show types              # List types
dfm show skills             # List agent skills
dfm context --json          # Full project context
```

### Validation
```bash
dfm validate                # Validate current flow
dfm validate --json         # JSON error output
```

## Common Patterns

### Verilator Simulation
```yaml
package:
  name: my_sim
  
  imports:
    - name: hdlsim.vlt
      as: sim
  
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      scope: root
      uses: sim.SimImage
      needs: [rtl]
      with:
        top: [my_top]
    
    - name: run
      scope: root
      uses: sim.SimRun
      needs: [build]
```

### Multi-Simulator Support
```yaml
with:
  simulator:
    type: str
    value: vlt

configs:
  - name: vlt
  - name: vcs
  - name: xsm
  - name: mti

imports:
  - name: hdlsim.vlt  # Default
    as: sim
```

## Error Handling

### Parse Errors
```bash
dfm validate --json
```
Returns structured error with file location.

### Missing Tasks
Check that:
1. Task is defined in the package
2. Import is correct
3. Task name is fully qualified

### Circular Dependencies
```bash
dfm validate
```
Reports circular dependency chains.

## Best Practices

1. **Always validate** - Run `dfm validate` before executing
2. **Use scope: root** - For tasks meant to be run directly
3. **Document tasks** - Add `doc` and `desc` fields
4. **Use imports** - Don't hardcode package paths
5. **Check skills** - Use `dfm show skills` to discover capabilities

## Agent Interaction Pattern

When a user asks about DFM:

1. **Gather context**: Run discovery commands
2. **Understand goal**: What does the user want to achieve?
3. **Propose solution**: Generate appropriate configuration
4. **Validate**: Run `dfm validate` on the solution
5. **Iterate**: Fix any errors and re-validate

## Do Not

- Guess task names or parameters
- Assume package availability without checking
- Generate configurations without validation
- Ignore error messages from validation

Always use the CLI to verify information and validate changes.
