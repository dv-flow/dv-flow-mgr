# CLI Reference (`dfm`)

Global options (before the subcommand): `--log-level {NONE,INFO,DEBUG}`,
`-D NAME=VALUE`, `-P FILE_OR_JSON`.

Top-level commands: `run`, `show`, `graph`, `validate`, `context`, `agent`,
`mcp`, `cache`, `daemon`, `worker`, `complete`, `util`.

## run

Execute one or more tasks (defaults to the package's root tasks).

```bash
dfm run [tasks...]
```

| Option | Meaning |
|---|---|
| `-j N` | Degree of parallelism (default: all cores). |
| `-c, --config NAME` | Select a configuration. |
| `-D NAME=VALUE` | Override a parameter (`param=…` or `task.param=…`). Repeatable. |
| `-P, --param-file FILE_OR_JSON` | Parameter overrides from a JSON file or inline JSON. |
| `--clean` | Clean the rundir before running. |
| `-f, --force` | Run all tasks, ignoring up-to-date status. |
| `-v, --verbose` | Show all tasks, including up-to-date ones. |
| `--base-rundir PATH` | Reuse artifacts from a pre-built rundir (tasks present there are treated as up to date). |
| `--root DIR` | Root directory for the flow. |
| `-u, --ui {log,progress,progressbar,tui}` | Console UI style. |
| `--runner NAME` | Runner backend (`local`, `lsf`, …; auto-detect by default). |
| `--runner-opt KEY=VALUE` | Runner option. Repeatable. |
| `--override TARGET=REPLACEMENT` | Replace a task (e.g. `pkg.Task=std.Null`). |

```bash
dfm run build
dfm run build -c debug -j 8
dfm run sim -D top_module=core -D top.build.opt_level=2
```

## show

Inspect the project. Subcommands:

```bash
dfm show packages [--search KW] [--json]
dfm show tasks    [--search KW] [--produces "type=…,attr=…"] [--json]
dfm show task <name> [--json]
dfm show types    [--json]
dfm show tags     [--search KW]
dfm show package  <name>
dfm show project  [--json]
dfm show skills   [<name>] [--search KW]
```

- `--produces "type=std.FileSet,filetype=verilog"` finds tasks by their declared
  outputs (great for wiring dataflow).
- `--json` on most subcommands gives machine-readable output for agents.

## graph

Generate the dependency graph of a task.

```bash
dfm graph <task> -o flow.dot       # then render with graphviz
dfm graph <task> -f <format>
```

## validate

Validate the flow, including produces/consumes compatibility.

```bash
dfm validate [--json]
```

## context

Output comprehensive project context for LLM agents (JSON by default).

```bash
dfm context --json
dfm context --imports --installed -v
```

Returns project metadata, tasks, types, and skills.

## agent

Launch an AI assistant with DV Flow context (skills/personas/tools/references).

```bash
dfm agent [tasks...] [-a copilot|codex|mock|native] [-m MODEL]
          [-c CONFIG] [--json] [--approval-mode never|auto|write]
```

`--json` prints the assembled context instead of launching; `--config-file`
dumps the assistant config for debugging.

## mcp

Start DFM as an MCP server (stdio) for editors/agents (Claude Desktop, Cursor,
VS Code, …).

```bash
dfm mcp [tasks...]
```

## cache

Manage the artifact/memento cache.

```bash
dfm cache init <cache_dir> [--shared]
```

## daemon / worker

Manage the background worker-pool daemon used by remote runners.

```bash
dfm daemon start
dfm daemon status
dfm daemon stop
```

`dfm worker` is internal (spawned by the daemon).

## util

Utility subcommands, including the JSON schema for editor validation:

```bash
dfm util schema > flow.schema.json
```

## complete

Shell-completion helper (emits completion candidates for a prefix).
