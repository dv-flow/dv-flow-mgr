# Developing Task Implementations (Python plugins)

Use this when a typed task is the right answer but none exists — i.e. you want
reusable, cached, discoverable behavior instead of repeated inline shell.

## Four approaches

1. **Inline pytask** — small Python embedded in YAML (prototyping).
2. **External pytask function** — an `async` function in a module (most common).
3. **PyTask class** — a dataclass-based implementation for complex tasks.
4. **PyPkg package factory** — define an entire package in Python.

## Function-based task (simplest reusable form)

```python
# my_pkg/tasks.py
from dv_flow.mgr import TaskDataResult

async def MyTask(runner, input) -> TaskDataResult:
    # input.name        -> task name
    # input.params.<p>  -> declared parameters
    # input.inputs      -> incoming data items
    # input.srcdir / input.rundir -> directories
    print(f"running {input.name} with p={input.params.my_param}")
    return TaskDataResult(status=0, changed=True)
```

```yaml
# flow.yaml
package:
  name: my_pkg
  tasks:
    - name: my_task
      shell: pytask
      run: my_pkg.tasks.MyTask
      with:
        my_param: { type: str, value: "default" }
```

`status != 0` signals failure. Attach `markers` to report diagnostics, and set
`changed` to indicate whether outputs changed (drives downstream up-to-date
decisions).

## Producing typed outputs

Return data items in the result so downstream tasks can consume them. Declare
the corresponding `produces:` in YAML so the output is discoverable and
validatable (see [dataflow.md](dataflow.md)).

## Incremental execution (mementos)

Pair a task with an `uptodate:` callable to make it skippable when inputs are
unchanged (the std library does this for `std.FileSet` / `std.SetEnv`). The
memento is persisted in the rundir cache and compared on the next run.

```yaml
- name: my_task
  shell: pytask
  run: my_pkg.tasks.MyTask
  uptodate: my_pkg.tasks.MyTaskUpToDate
```

## Packaging a plugin

Ship tasks as a normal Python package whose installed files include a
`flow.dv`/`flow.yaml` describing the package, so `dfm` can discover it. Use
`dfm show packages` / `dfm show tasks` to confirm discovery after install.

> For the full API surface (TaskDataResult fields, runner/exec helpers, PyTask
> classes, PyPkg factories, memento patterns), consult the DV Flow Manager
> documentation. This file is an orientation, not the complete API reference.
