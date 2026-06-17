# Authoring Tasks

## Using a task

Most tasks inherit from an existing task with `uses:` and customize via `with:`:

```yaml
- name: banner
  uses: std.Message
  with:
    msg: "Hello"
```

## Overriding a task

Within a package you can replace a task's definition with `override:`:

```yaml
- override: build
  with:
    msg: "Building in debug mode"
```

## Extending a task

Extensions add parameters, dependencies, or attributes to an existing task
(often one imported from another package) without replacing it. See the user
guide / `configs.md` for `extensions:` usage in configurations.

## Embedding shell commands

When no typed task fits, run shell directly. Specify the shell with `shell:` and
the command with `run:` (an inline block or a script path). No `uses:` is
required.

```yaml
tasks:
  - name: run_script
    shell: bash
    run: ./scripts/process.sh          # script path

  - root: build
    shell: bash
    run: |                             # inline multi-line script
      echo "compiling..."
      make build
```

Supported shells include `bash`, `sh`, `python` (interpreter), and `pytask`
(Python task with task context — see [task_development.md](task_development.md)).

### Referencing variables inside `run:`

There are **two** mechanisms, and they expand at different times:

1. **DFM expressions** — `${{ ... }}`. DFM substitutes these *before* the script
   runs. Inside a `run:` body you can reference:
   - task parameters by bare name (`${{ defines }}`)
   - package parameters by bare name (`${{ top_module }}`)
   - the task run directory (`${{ rundir }}`)
   - inputs at runtime (`${{ inputs }}`, `${{ inputs | length }}`)

2. **Shell environment variables** — expanded by the shell at runtime. DFM
   injects `$TASK_SRCDIR` (the task's source directory) and `$TASK_RUNDIR` (its
   run directory). Variables set by `std.SetEnv` upstream are also available.

```yaml
- root: build
  shell: bash
  with:
    defines: { type: list, value: [] }
  run: |
    echo "Building ${{ top_module }} in ${{ rundir }}"
    echo "source dir: $TASK_SRCDIR"
    echo "defines: ${{ defines }}"
```

**Gotchas:**

- Task parameters are **not** exported as plain shell variables. Use
  `${{ name }}`, not `$name`, to read a parameter.
- The task runs with its working directory set to its run directory, so write
  outputs relative to the cwd (or to `${{ rundir }}` / `$TASK_RUNDIR`).

### Emitting outputs from a shell task

To produce a typed dataset, declare `produces:` and print the data item as JSON
on stdout:

```yaml
- root: build
  shell: bash
  produces:
    - type: std.FileSet
      filetype: buildManifest
  run: |
    echo "manifest" > build.manifest
    echo '{"type":"std.FileSet","filetype":"buildManifest","basedir":"'"${{ rundir }}"'","files":["build.manifest"]}'
```

## When to use shell vs a typed task

Prefer an existing typed task (`std.*` or a plugin task) whenever one exists — it
gives you typed dataflow, caching, and discoverability for free. Drop to raw
shell only for genuine one-offs or tools without a dedicated task. If you find
yourself repeating the same shell across tasks, consider a Python task plugin
([task_development.md](task_development.md)).
