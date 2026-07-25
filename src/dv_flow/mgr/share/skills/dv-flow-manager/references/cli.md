# CLI Reference (`dfm`)

Global options (before the subcommand): `--log-level {NONE,INFO,DEBUG}`,
`-D NAME=VALUE`, `-P FILE_OR_JSON`, `--package-map FILE` (map a package name to
its flow file for resolving imports by name; repeatable).

Top-level commands: `run`, `show`, `graph`, `validate`, `context`, `agent`,
`mcp`, `cache`, `daemon`, `worker`, `complete`, `util`.

## run

Execute exactly **one** root task. With no task, lists the package's root tasks.
The single-task restriction is what makes the per-task front-end behavior below
(task arguments, `--help`, a declared `summary:`) well defined.

```bash
dfm run            # list the root tasks
dfm run <task>
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
| `--report DIR` | After the run, write a diagnostics bundle (per-task logs, markers, status) to `DIR` for publishing as a CI artifact. |
| `--run-id ID` | Identifier for this run's output directory (`rundir/out/<ID>`). |
| `--no-summary` | Suppress the end-of-run task summary on the console. |
| `--summary-file PATH` | Also write the summary to `PATH` (`.md` → markdown, else plain text). Written even with `--no-summary`. |

Every run prints an end-of-run **task summary** — counts plus a row per task that
did something, with its markers. It renders identically under every UI, so piped
and CI runs get it too. With `--report DIR` it is also written to the bundle as
`summary.md` and inlined into `report.md`.

```bash
dfm run build
dfm run build -c debug -j 8
dfm run sim -D top_module=core -D top.build.opt_level=2
```

### Task arguments

A task that declares a `cli:` block gets **first-class flags**:

```yaml
- name: run-tests
  scope: root
  desc: Run the UVM regression suite
  cli:
    args:
    - name: seed        # --seed
      short: s          # -s
    - name: sim
      choices: [vlt, vcs, xsim]
  with:
    seed: { type: int, value: 0,   doc: Base random seed }
    sim:  { type: str, value: vlt, doc: Simulator backend }
```

```bash
dfm run run-tests --seed 42 --sim vcs
dfm run run-tests -- --seed 42     # '--' is supported but not required
dfm run run-tests --help           # the task's arguments, not dfm's
```

Everything but `name` defaults from the parameter (help from its `doc`/`desc`,
type and default from its declaration), so the common case is `- name: seed`.
`cli:` is inherited along `uses:`, nearest declaration winning, and a derived
block **replaces** the inherited one rather than merging with it.

Precedence, low to high: parameter default → `-P` file → `-D` → `--flag`. Note
the two scope differently on purpose: `--seed` sets only the invoked root, while
a bare `-D seed=42` reaches every task that has a `seed` parameter.

A `cli:` arg that names a missing parameter, duplicates another, or collides
with a dfm option is a **load-time error**, so a future dfm option can never
silently steal a flag from a flow.

## show

Inspect the project. Subcommands:

```bash
dfm show packages [--search KW] [--json]
dfm show tasks    [--search KW] [--produces "type=…,attr=…"] [--json]
dfm show task <name> [--usage] [--json]
dfm show types    [--json]
dfm show tags     [--search KW]
dfm show package  <name>
dfm show project  [--json]
dfm show skills   [<name>] [--search KW]
```

- `--produces "type=std.FileSet,filetype=verilog"` finds tasks by their declared
  outputs (great for wiring dataflow).
- `--json` on most subcommands gives machine-readable output for agents.
- `show task --usage` gives the *CLI-shaped* view — how to invoke the task and
  what arguments it takes — instead of the data-shaped detail view. `--json`
  combines with it and yields an `args` array (`param`, `type`, `default`,
  `help`, `define`), which is what a completion script or agent should read.
- Parameters inherited through `uses:` are listed too, and are settable with
  `-D` like any other.

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

Utility subcommands. `schema` emits the JSON schema for editor validation;
`workspace` dumps the resolved project as JSON.

```bash
dfm util schema -o flow.schema.json   # or: dfm util schema > flow.schema.json
dfm util schema --generate            # regenerate from models (dev)
dfm util workspace                    # resolved project as JSON
```

## complete

Shell-completion helper (emits completion candidates for a prefix).

```bash
dfm complete <prefix>                 # task names
dfm complete --task <name> <prefix>   # that task's cli: flags
```
