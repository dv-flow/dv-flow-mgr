---
name: dv-flow-manager
description: Author and run idiomatic DV Flow Manager (dfm) flows for silicon design & verification. Use when creating or editing flow.yaml files, structuring a DFM project, wiring task dataflow, defining configs, or running dfm commands.
---

# DV Flow Manager (dfm)

DV Flow Manager is a YAML-based build system and execution engine for silicon
design and verification. You describe **tasks** and the **dataflow** between
them; DFM builds a dependency DAG, executes it concurrently, and skips work
that is already up to date.

## When to use this skill

- Creating or editing `flow.yaml` files (package / fragment definitions).
- Structuring a DFM project (fragments, namespaces, visibility).
- Wiring tasks together with dataflow (`needs` / `produces` / `consumes`).
- Defining build variants with `configs`.
- Running, inspecting, or validating flows with the `dfm` command.
- Running `dfm` from inside an LLM-driven `std.Agent` task.

## Golden rules (read first)

1. **Always use `flow.yaml`.** (`.dv` / `.yml` / `.toml` are also recognized,
   but `flow.yaml` is the convention for new work.)
2. **Co-locate definitions with sources.** Tasks describing `rtl/` live in
   `rtl/flow.yaml`, not in the root file.
3. **Distribute content with a fragment hierarchy.** The root file uses
   `package:`; every other file uses `fragment:` and is pulled in via
   `fragments:`.
4. **Use fragment namespaces.** Give a fragment a `name:` to namespace its
   tasks as `<package>.<name>.<task>` (e.g. `top.rtl.files`). The namespace is
   always one level deep, regardless of file nesting.
5. **Hide by default; expose a deliberate API.** Mark entry points `root`,
   cross-package tasks `export`, helpers `local`; leave everything else
   unscoped (package-visible).
6. **Connect tasks with dataflow, not paths.** Use `needs` for *direct* deps
   only; declare typed `produces`/`consumes` so tasks are discoverable and
   validatable. Use `feeds` to inject data without editing the target.
7. **Use `configs` for variants** (debug/release, tool/vendor, regression),
   not duplicated files. Select with `-c <name>`.
8. **Parameterize with `with:` + `${{ }}`**; never hard-code values.
9. **Embed shell directly when no task fits** (`shell: bash` + `run:`), but
   prefer an existing typed task whenever one exists.
10. **Reuse library skills and tasks before authoring** — discover what is
    installed first (see below) and suggest a fitting library skill to the user.
11. **Validate and visualize before declaring done**: `dfm validate` and
    `dfm graph <task>`.

## Minimal flow

```yaml
package:
  name: my_design
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
      produces:
        - type: std.FileSet

    - root: build
      uses: std.Message
      needs: [rtl]
      consumes:
        - type: std.FileSet
      with:
        msg: "Building from collected sources"
```

Run it with `dfm run build`.

## Project structure at a glance

```
top/
  flow.yaml          # package: top   (root entry points, configs, params)
  rtl/flow.yaml      # fragment name: rtl    -> top.rtl.*
  tb/flow.yaml       # fragment name: tb     -> top.tb.*
  tests/flow.yaml    # fragment name: tests  -> top.tests.*
```

A complete, runnable, std-only version is in
[`examples/golden/`](examples/golden/flow.yaml). See
[references/project_layout.md](references/project_layout.md).

## Visibility cheatsheet

| Marker / scope | Meaning |
|---|---|
| `root: name` (or `scope: root`) | Entry point; listed by `dfm run`. |
| `export: name` | Visible to other packages' `needs`. |
| `local: name` | Visible only within its fragment / compound body. |
| `name:` (no scope) | Package-visible only (the default). |

Use inline markers (`root:`/`export:`/`local:`) instead of `name:` + `scope:`.
Only one of `name`/`root`/`export`/`local`/`override` per task. Details:
[references/visibility.md](references/visibility.md).

## Dataflow cheatsheet

- `needs: [a, b]` — direct dependencies (transitive resolve automatically).
- `feeds: [pkg.task]` — inverse of `needs`; inject output into another task.
- `produces: [patterns]` — typed output datasets this task creates.
- `consumes: all | none | [patterns]` — which inputs reach the implementation.
- `passthrough: all | none | unused | [patterns]` — which inputs forward to output.

Matching is **OR** across patterns and **subset** (a consumer may be less
specific than the producer). Details:
[references/dataflow.md](references/dataflow.md).

## Configs cheatsheet

```yaml
configs:
  - name: debug
    tasks:
      - local: debug_args
        uses: std.Message
        with: { msg: "+define+DEBUG" }
        feeds: [top.build]      # inject into build only under -c debug
```

Select with `dfm run build -c debug`. Extend list params with
`append:`/`prepend:`. Details: [references/configs.md](references/configs.md).

## Expressions

Use `${{ }}` for dynamic values; reference a parameter by its bare name:

```yaml
msg: "Building ${{ top_module }}"
count: "${{ inputs | length }}"
flag: "${{ debug_level > 0 }}"
```

## Shell commands & variables

Embed shell directly on a task with `shell: bash` + `run:` (inline `|` block or
a script path). Inside `run:` you can reference:

- **DFM expressions** `${{ ... }}` — task params and package params by bare
  name, plus `${{ rundir }}` and (at runtime) `${{ inputs }}`. DFM substitutes
  these before the script runs.
- **Shell environment variables** — `$TASK_SRCDIR`, `$TASK_RUNDIR` (and any set
  via `std.SetEnv`). The shell expands these.

```yaml
- root: build
  shell: bash
  with:
    defines: { type: list, value: [] }
  run: |
    echo "Building ${{ top_module }} in ${{ rundir }} (src=$TASK_SRCDIR)"
    echo "defines: ${{ defines }}"
```

Note: task parameters are **not** exported as plain shell variables — reference
them via `${{ name }}`, not `$name`. Prefer a typed task over raw shell when one
exists. Details: [references/authoring_tasks.md](references/authoring_tasks.md).

## Discovering & reusing library skills (do this first)

Many installed plugin packages ship reusable **skills** (DataSet types tagged
`std.AgentSkillTag`) and **tasks**. Before authoring anything, discover what is
available and reuse it — and suggest a relevant library skill to the user:

```bash
dfm show skills                 # list available agent skills
dfm show skills --search uvm    # search skills by keyword
dfm show skills <name>          # show one skill's documentation
dfm show tasks --search sim     # find reusable tasks by keyword
dfm show tasks --produces "type=std.FileSet,filetype=verilog"  # find by output
```

See [references/agent_runtime.md](references/agent_runtime.md).

## Essential commands

```bash
dfm run [tasks...]           # execute tasks (default = listed root tasks)
dfm run -c debug build       # run with the 'debug' config
dfm run -D name=value task   # override a parameter
dfm show tasks               # list visible tasks
dfm show task <name>         # task detail (params, needs, produces)
dfm show project             # project structure
dfm graph <task> -o flow.dot # visualize the DAG
dfm validate                 # validate the flow (checks dataflow)
```

Full CLI: [references/cli.md](references/cli.md).

## Recommended authoring workflow

1. **Survey** — `dfm show project`, `dfm show tasks`, `dfm context --json`.
2. **Discover library skills & tasks** — `dfm show skills [--search]`,
   `dfm show tasks --search/--produces`; suggest a fitting library skill.
3. **Locate** — create/extend the `flow.yaml` co-located with the sources.
4. **Reuse before authoring** — compose a discovered task/skill; prefer a typed
   task over raw shell.
5. **Define tasks** — `uses:` a base; `needs` (direct only); typed
   `produces`/`consumes`; parameterize with `with:` / `${{ }}`.
6. **Set visibility** — `root` / `export` / `local`; leave internals unscoped.
7. **Wire variants** — put differences in `configs:` via `feeds` / params.
8. **Validate** — `dfm validate` (fix dataflow warnings); `dfm graph <task>`.
9. **Run** — `dfm run <root>` (`-c <config>`, `-D` as needed).

## Running inside an Agent task

When `dfm` runs inside a `std.Agent` task, the `DFM_SERVER_SOCKET` environment
variable is set and `dfm` automatically talks to the parent session (shared
parallelism, cache, and logs). The same `run` / `show` / `validate` / `context`
commands work. See [references/agent_runtime.md](references/agent_runtime.md).

## Reference index

- [concepts.md](references/concepts.md) — packages, tasks, dataflow, types, the execution model
- [project_layout.md](references/project_layout.md) — fragments, nesting, namespaces, qualified names
- [visibility.md](references/visibility.md) — scopes, inline markers, API design
- [dataflow.md](references/dataflow.md) — needs/feeds/produces/consumes/passthrough, matching, discovery
- [configs.md](references/configs.md) — variants, overrides, extensions, params, append/prepend
- [authoring_tasks.md](references/authoring_tasks.md) — using/overriding/extending tasks, shell + variables
- [stdlib.md](references/stdlib.md) — the `std.*` task catalog
- [cli.md](references/cli.md) — the full `dfm` command-line interface
- [agent_runtime.md](references/agent_runtime.md) — server mode + discovering/reusing library skills
- [task_development.md](references/task_development.md) — writing Python task plugins (advanced)
- [`examples/golden/`](examples/golden/flow.yaml) — a complete, runnable, std-only project

To get the JSON schema for editor validation: `dfm util schema > flow.schema.json`.
