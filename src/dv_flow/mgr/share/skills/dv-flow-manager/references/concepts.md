# Core Concepts

## Packages

A **package** is a parameterized namespace that defines tasks, types, and
configurations. A package is declared in a root `flow.yaml` with the `package:`
key:

```yaml
package:
  name: my_pkg
  with:
    debug:
      type: bool
      value: false
  tasks:
    - name: t1
      uses: std.Message
      with: { msg: "hello" }
```

Tasks within a package are referenced as `package_name.task_name`
(e.g. `my_pkg.t1`). Within the same package you may use the short name (`t1`).

## Tasks

A **task** is a processing step. Most tasks inherit behavior from an existing
task with `uses:`:

```yaml
- name: my_task
  uses: std.Message
  with:
    msg: "Hello!"
```

A task may instead embed shell directly (`shell: bash` + `run:`) or reference a
Python implementation (`shell: pytask` + `run: module.Class`). See
[authoring_tasks.md](authoring_tasks.md).

## Dataflow

Tasks communicate through **typed data items**, not global variables.

- A task's `needs` list names the tasks it depends on directly. DFM resolves
  transitive dependencies automatically.
- Each task receives the outputs of its dependencies as **inputs** and emits its
  own **outputs**.
- `produces` / `consumes` declare typed patterns describing those outputs and
  inputs. They enable discovery (`dfm show tasks --produces ...`) and validation
  (`dfm validate`).

The **execution graph** (which tasks run, in what order) is statically known
before execution. The **data** flowing between tasks is only known at runtime.
See [dataflow.md](dataflow.md).

## Types

Data items have types. The standard library defines `std.DataItem` and
`std.FileSet` (a set of files with a `filetype`, base directory, include/exclude
globs, incdirs, defines, and attributes). Packages can define additional types
under a `types:` key. Tags (`std.Tag` and its subtypes such as
`std.AgentSkillTag`) classify data items and tasks.

## The execution model

1. DFM loads the root package and all its fragments/imports.
2. A configuration (`-c`) is merged in, if selected.
3. The task graph for the requested root task(s) is built.
4. Tasks execute concurrently, honoring `needs` ordering and the jobserver's
   parallelism limit (`-j`).
5. Each task's result is cached (a *memento*). On the next run, a task whose
   inputs and parameters are unchanged is **up to date** and is skipped.

## Visibility

Visibility controls which tasks are entry points, which cross package
boundaries, and which are internal. Default to hiding tasks and expose a small,
deliberate API. See [visibility.md](visibility.md).

## HDL tooling (requires a plugin)

The standard library is tool-agnostic. Real HDL flows use plugin packages such
as `dv-flow-libhdlsim`, which add tasks like `hdlsim.vlt.SimImage` and
`hdlsim.vlt.SimRun`:

```yaml
# Requires: pip install dv-flow-libhdlsim
- name: sim
  uses: hdlsim.vlt.SimImage
  needs: [rtl]
  with: { top: [top] }
```

Discover what a given installation provides with `dfm show tasks` and
`dfm show packages`.
