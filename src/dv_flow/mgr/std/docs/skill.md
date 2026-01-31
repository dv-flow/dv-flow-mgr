# Standard Library (std)

The std package provides core tasks, types, and utilities for DV Flow workflows.

## Core Concepts

### Tasks
Tasks are the building blocks of DV Flow workflows. They define actions to be executed,
their dependencies, and their outputs.

### Types
Types define data structures that can be passed between tasks and configure task behavior.

### Tags
Tags are used to categorize and filter tasks, types, and packages.

## Key Tasks

### FileSet
Creates a fileset from a list of files or glob patterns.

```yaml
tasks:
  - name: rtl
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "src/**/*.sv"
      incdirs: ["src/include"]
```

### CreateFile
Creates one or more files in the run directory from literal content in the .dv file.

```yaml
tasks:
  - name: config
    uses: std.CreateFile
    with:
      filename: config.vh
      content: |
        `define WIDTH 32
        `define DEPTH 256
      type: verilogInclude
```

### Running Shell Commands

Execute shell commands by specifying `shell: bash` and `run:`.

```yaml
tasks:
  - name: preprocess
    shell: bash
    run: python3 generate_rtl.py
```

### Prompt
Executes an AI assistant with a specified prompt and collects structured results.

```yaml
tasks:
  - name: analyze
    uses: std.Prompt
    with:
      user_prompt: "Analyze the test results and suggest improvements"
      result_file: analysis.json
```

### SetEnv
Sets environment variables for use by other tasks.

```yaml
tasks:
  - name: env
    uses: std.SetEnv
    with:
      setenv:
        TOOL_HOME: /opt/tools
      prepend_path:
        PATH: /opt/tools/bin
```

## Key Types

### DataItem
Base type for all data items that can be passed between tasks.

### FileSet
Represents a collection of files with associated metadata (type, include directories, defines).

### AgentSkill
Defines agent skills for LLM agent discovery. Packages should define an AgentSkill
to expose their capabilities to AI agents.

### AgentTool
Specifies MCP servers or tools that agents can use.

### AgentReference
Specifies reference materials for agents.

## Package Structure

```yaml
package:
  name: my_package
  desc: Description of the package
  
  imports:
    - name: std
  
  tasks:
    - name: my_task
      uses: std.FileSet
      with:
        include: "*.sv"
  
  types:
    - name: MyType
      uses: std.DataItem
```

## Best Practices

1. **Use FileSet for source files**: FileSet provides structured metadata about files
2. **Leverage task dependencies**: Use `needs` to specify task dependencies
3. **Use configs for variations**: Define configs to support different build scenarios
4. **Document your tasks**: Add `doc` and `desc` fields to tasks and types
5. **Tag appropriately**: Use tags to make your tasks and types discoverable
