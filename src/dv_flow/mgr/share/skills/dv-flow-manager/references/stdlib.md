# Standard Library (`std.*`)

These tasks and types ship with DFM and require no plugins. Inspect any of them
live with `dfm show task std.<Name>`.

## Tasks

### std.Message
Prints a message. Useful as an entry point, marker, or for `feeds`.

```yaml
- name: hello
  uses: std.Message
  with:
    msg: "Hello, ${{ top_module }}"
```

### std.FileSet
Collects files from glob patterns into a typed fileset (the workhorse producer).

```yaml
- export: files
  uses: std.FileSet
  with:
    base: "."                    # base directory (default ".")
    type: systemVerilogSource    # filetype tag applied to the set
    include: ["*.sv", "*.svh"]   # globs (string or list)
    exclude: []                  # globs to drop
    incdirs: []                  # include directories
    defines: []                  # preprocessor defines
    attributes: []               # free-form tags (e.g. ["uvm"])
```
Produces a `std.FileSet`; consumes nothing.

### std.CreateFile
Writes a file in the run directory from literal content and outputs a fileset
referencing it.

```yaml
- name: gen_cfg
  uses: std.CreateFile
  with:
    filename: "config.json"
    content: |
      {"mode": "release"}
    type: jsonData          # filetype for the output fileset
    incdir: false           # if true, mark its dir as an include dir
```

### std.SetEnv
Sets environment variables for downstream tasks. Supports glob expansion and
path append/prepend.

```yaml
- name: tool_env
  uses: std.SetEnv
  with:
    setenv:
      TOOL_HOME: /opt/tools/mytool
    append_path:
      PATH: /opt/tools/mytool/bin
    prepend_path:
      LD_LIBRARY_PATH: /opt/tools/mytool/lib
```

### std.SetFileType
Re-tags input filesets with a new `filetype`. Consumes `std.FileSet`.

```yaml
- name: as_verilog
  uses: std.SetFileType
  needs: [raw]
  with: { filetype: verilog }
```

### std.IncDirs
Builds a list of include directories from a set of input files.

### std.Agent
Runs an AI assistant with a prompt and collects a structured JSON result.
Supported assistants include GitHub Copilot (`copilot`) and OpenAI Codex
(`codex`); auto-probes if unspecified. The assistant must write a valid JSON
result file or the task fails. Parameters include `system_prompt`, `prompt`,
`assistant`, sandbox/approval modes, and `max_iterations`.

### std.Null
A no-op task. Useful as an aggregation point or placeholder.

### std.RunTasks
Dynamically schedules tasks specified by `std.TaskRunSpec` inputs into the
current execution, with proper dependencies (advanced).

## Types & tags

- **std.DataItem** — base data item (`type`).
- **std.FileSet** — a set of files (`filetype`, `basedir`, `files`, ...).
- **std.Tag** and subtypes — classify tasks/data items:
  - `std.AgentSkillTag`, `std.AgentToolTag`, `std.AgentPersonaTag`,
    `std.AgentReferenceTag` — mark agent resources (see
    [agent_runtime.md](agent_runtime.md)).
  - `std.ResourceTag` — mark resource requirements.

> The std library is intentionally tool-agnostic. HDL simulation/synthesis tasks
> come from plugin packages such as `dv-flow-libhdlsim` (`hdlsim.vlt.SimImage`,
> `hdlsim.vlt.SimRun`, ...). Use `dfm show packages` / `dfm show tasks` to see
> what is installed.
