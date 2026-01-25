# DV Flow Manager Standard Library

The `std` package provides fundamental tasks that are always available without explicit import.

## std.FileSet

Collect files matching patterns into a typed fileset.

### Example

```yaml
- name: rtl_sources
  uses: std.FileSet
  with:
    type: systemVerilogSource
    base: src/rtl
    include: "*.sv"
    exclude: "*_tb.sv"
    incdirs: [include, rtl/include]
    defines: [SYNTHESIS]
    attributes: [rtl]
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `type` | Yes | Filetype of produced fileset (e.g., `systemVerilogSource`, `verilogSource`) |
| `base` | No | Base directory for file search (default: task source directory) |
| `include` | Yes | Glob patterns for files to include |
| `exclude` | No | Glob patterns for files to exclude |
| `incdirs` | No | Include directories for consumers |
| `defines` | No | Preprocessor defines for consumers |
| `attributes` | No | Tags for filtering (e.g., `[rtl]`, `[testbench, uvm]`) |

### Consumes/Produces

- **Consumes**: none
- **Produces**: `std.FileSet` data item

### Common Filetypes

- `systemVerilogSource` - SystemVerilog files
- `verilogSource` - Verilog files
- `vhdlSource` - VHDL files
- `cSource` - C source files
- `cppSource` - C++ source files
- `text` - Generic text files

---

## std.Message

Display a message during task execution.

### Example

```yaml
- name: hello
  uses: std.Message
  with:
    msg: "Hello, World!"

- name: status
  uses: std.Message
  with:
    msg: "Building version ${{ version }}"
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `msg` | No | Message to display (default: empty) |

### Consumes/Produces

- **Consumes**: all
- **Produces**: Passes through all inputs

---

## std.CreateFile

Create a file with specified content.

### Example

```yaml
- name: config_file
  uses: std.CreateFile
  with:
    type: text
    filename: config.txt
    content: |
      # Generated configuration
      debug = true
      level = 5
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `type` | Yes | Filetype of produced file |
| `filename` | Yes | Name of file to create |
| `content` | Yes | Content to write to file |
| `incdir` | No | If true, add output directory as include directory |

### Consumes/Produces

- **Consumes**: none
- **Produces**: `std.FileSet` with single file

---

## std.Exec

Execute a shell command.

### Example

```yaml
- name: run_script
  uses: std.Exec
  with:
    command: "./scripts/process.sh"
    shell: bash

- name: conditional_run
  uses: std.Exec
  with:
    command: "make all"
    when: changed
    timestamp: "build/timestamp.txt"
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `command` | Yes | Shell command to execute |
| `shell` | No | Shell to use (default: `bash`) |
| `when` | No | `always` (default) or `changed` |
| `timestamp` | No | File to check for timestamp-based execution |

### Consumes/Produces

- **Consumes**: all
- **Produces**: Passes through all inputs

---

## std.SetEnv

Set environment variables for downstream tasks.

### Example

```yaml
- name: tool_env
  uses: std.SetEnv
  with:
    setenv:
      TOOL_HOME: /opt/tools
      LICENSE_FILE: /opt/licenses/license.dat
    append_path:
      PATH: /opt/tools/bin
    prepend_path:
      LD_LIBRARY_PATH: /opt/tools/lib
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `setenv` | No | Map of environment variables to set |
| `append_path` | No | Map of PATH-like variables to append |
| `prepend_path` | No | Map of PATH-like variables to prepend |

### Glob Expansion

Values with glob patterns are expanded:

```yaml
with:
  setenv:
    MY_LIBS: "libs/*/lib"  # Expands to all matching paths
```

### Consumes/Produces

- **Consumes**: all
- **Produces**: `std.Env` data item

---

## std.SetFileType

Change the filetype of input filesets.

### Example

```yaml
- name: verilog_files
  uses: std.FileSet
  with:
    include: "*.v"
    type: verilogSource

- name: as_sv
  uses: std.SetFileType
  needs: [verilog_files]
  with:
    filetype: systemVerilogSource
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `filetype` | Yes | New filetype to assign |

### Consumes/Produces

- **Consumes**: `std.FileSet` items only
- **Produces**: Modified `std.FileSet` items

---

## std.IncDirs

Extract include directories from input filesets.

### Example

```yaml
- name: rtl_files
  uses: std.FileSet
  with:
    include: "*.sv"
    incdirs: [include, rtl/include]

- name: get_incdirs
  uses: std.IncDirs
  needs: [rtl_files]
```

### Parameters

None.

### Consumes/Produces

- **Consumes**: `std.FileSet` items
- **Produces**: Data item with collected include directories

---

## std.Prompt

Execute an AI assistant with a prompt and collect structured results.

### Example

```yaml
- name: generate_test
  uses: std.Prompt
  with:
    user_prompt: "Generate unit tests for the parser module"
    assistant: copilot
```

### Custom System Prompt

```yaml
- name: code_review
  uses: std.Prompt
  with:
    system_prompt: |
      You are a code review assistant.
      Input files: ${{ inputs }}
      Write results to ${{ result_file }} as JSON with structure:
      {
        "status": 0,
        "changed": true,
        "output": [],
        "markers": [{"msg": "...", "severity": "info"}]
      }
    user_prompt: "Review the input files for coding standards"
    result_file: "review.result.json"
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `system_prompt` | No | System prompt template (has default) |
| `user_prompt` | No | User's request |
| `result_file` | No | Expected result file (default: `{name}.result.json`) |
| `assistant` | No | AI assistant: `copilot` (default), `openai`, `claude` |
| `assistant_config` | No | Assistant-specific configuration |

### Template Variables

In prompts:
- `${{ inputs }}` - JSON of input data from upstream tasks
- `${{ name }}` - Current task name
- `${{ result_file }}` - Expected result filename

### Required Result Format

The AI must create a JSON file:

```json
{
  "status": 0,
  "changed": true,
  "output": [
    {
      "type": "std.FileSet",
      "filetype": "pythonSource",
      "basedir": ".",
      "files": ["generated.py"]
    }
  ],
  "markers": [
    {"msg": "Generated 1 file", "severity": "info"}
  ]
}
```

### Consumes/Produces

- **Consumes**: all (available via `${{ inputs }}`)
- **Produces**: As specified in result JSON

---

## Common Patterns

### File Collection Pipeline

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
      attributes: [testbench]
```

### Environment + Execution

```yaml
tasks:
  - name: setup
    uses: std.SetEnv
    with:
      setenv:
        SIMULATOR: verilator
      append_path:
        PATH: /opt/verilator/bin
  
  - name: run
    uses: std.Exec
    needs: [setup]
    with:
      command: "verilator --version"
```

### File Generation + Collection

```yaml
tasks:
  - name: generate
    rundir: inherit
    body:
      - name: create_config
        uses: std.CreateFile
        with:
          type: text
          filename: config.sv
          content: |
            `define CONFIG_WIDTH 32
      
      - name: collect
        uses: std.FileSet
        needs: [create_config]
        with:
          type: systemVerilogSource
          include: "*.sv"
```

### Conditional Messages

```yaml
tasks:
  - name: status
    uses: std.Message
    body:
      - name: debug_msg
        uses: std.Message
        iff: ${{ debug }}
        with:
          msg: "Debug mode enabled"
      
      - name: release_msg
        uses: std.Message
        iff: ${{ not debug }}
        with:
          msg: "Release mode"
```
