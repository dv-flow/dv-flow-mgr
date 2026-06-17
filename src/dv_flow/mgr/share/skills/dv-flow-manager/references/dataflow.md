# Dataflow

Tasks are connected by **dependency-based dataflow**. A task receives the
outputs of its dependencies as inputs, and emits its own outputs.

## needs

`needs` declares **direct** dependencies. Transitive dependencies are resolved
automatically — never flatten a chain into one big `needs` list.

```yaml
- name: tb
  uses: std.FileSet
  needs: [rtl]            # tb depends on rtl
```

Reference tasks by short name within the package/namespace, or by fully-qualified
name (`pkg.task`, `pkg.frag.task`) across boundaries.

## feeds (inverse of needs)

`feeds` declares that this task's output should be injected into another task,
without editing that target. These are equivalent:

```yaml
- name: sources
  uses: std.FileSet
  feeds: [compile]        # "I feed compile"

- name: compile
  needs: [sources]        # "I need sources"
```

`feeds` is especially useful inside `configs` to add data/arguments to existing
tasks. Feed targets use fully-qualified names (`pkg.task`).

## produces

Declares the typed output datasets a task creates. Patterns are matched by
their attributes:

```yaml
produces:
  - type: std.FileSet
    filetype: verilog
```

## consumes

Controls which inputs reach the task implementation:

- `consumes: all` — all inputs (default for many tasks)
- `consumes: none` — no inputs reach the implementation
- `consumes: [patterns]` — only matching inputs

```yaml
consumes:
  - type: std.FileSet
    filetype: verilog
```

## passthrough

Controls which inputs are forwarded to the task's *output* (in addition to what
the task itself produces):

- `passthrough: all` — forward all inputs
- `passthrough: none` — forward nothing
- `passthrough: unused` — forward only inputs not consumed
- `passthrough: [patterns]` — forward matching inputs

## Pattern matching rules

- **OR logic:** if *any* consume pattern matches *any* produce pattern, the
  tasks are compatible.
- **Subset matching:** a consumer may be *less* specific than the producer.

```yaml
# Producer (specific)
produces:
  - type: std.FileSet
    filetype: verilog
    vendor: synopsys

# Consumer (less specific) — MATCHES
consumes:
  - type: std.FileSet
    filetype: verilog
```

Common `std.FileSet` attributes: `filetype`, `base`, plus any custom attributes
you attach via `attributes:`. Custom data types may carry arbitrary attributes.

## Discovery

Find tasks by what they produce:

```bash
dfm show tasks --produces "type=std.FileSet,filetype=verilog" --json
dfm show task <name> --json        # inspect a task's produces/consumes
```

## Validation

`dfm validate` flags produces/consumes mismatches:

```
WARNING: Task 'Consumer' consumes [{'type':'std.FileSet','filetype':'vhdl'}]
         but 'Producer' produces [{'type':'std.FileSet','filetype':'verilog'}].
```

Fixes: relax the consumer pattern, pick a different producer, insert a converter
task, or adjust a parameter so the producer emits the needed type.

## Referencing inputs at runtime

Inside a `run:` body, `${{ inputs }}` expands to the JSON of the task's inputs
at execution time, and jq-style builtins work on it
(e.g. `${{ inputs | length }}`). These are deferred until the task runs.
