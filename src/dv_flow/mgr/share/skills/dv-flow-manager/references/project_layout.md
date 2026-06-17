# Project Layout: Fragments & Namespaces

A non-trivial DFM project should be **distributed across multiple files**, each
co-located with the sources it describes. This keeps task definitions next to
the code they operate on and keeps any single file readable.

## package vs fragment

- The **root** file uses `package:` and is the only file that may carry
  package-level `name`, `with` (params), and `desc`.
- Every **other** file uses `fragment:` and is pulled in via a `fragments:` list.

```yaml
# top/flow.yaml  (root)
package:
  name: top
  fragments:
    - rtl/flow.yaml
    - tb/flow.yaml
```

```yaml
# top/rtl/flow.yaml
fragment:
  tasks:
    - name: files
      uses: std.FileSet
      with: { type: systemVerilogSource, include: "*.sv" }
```

Fragment paths are always relative to the file that contains the `fragments:`
list.

## Allowed fragment fields

| Field | Allowed in fragment? |
|---|---|
| `tasks` | yes |
| `types` | yes |
| `configs` | yes |
| `imports` | yes |
| `filters` | yes |
| `fragments` | yes (nesting) |
| `name` | yes (creates a namespace — see below) |
| `with` (params) | **no** (root package only) |
| `desc` | **no** (root package only) |

## Fragment namespaces

Give a fragment a `name:` to **sub-namespace** all of its tasks as
`<package>.<fragment-name>.<task>`:

```yaml
# top/rtl/flow.yaml
fragment:
  name: rtl
  tasks:
    - export: files       #  -> top.rtl.files
      uses: std.FileSet
      with: { type: systemVerilogSource, include: "*.sv" }
```

```yaml
# top/tb/flow.yaml
fragment:
  name: tb
  tasks:
    - export: files       #  -> top.tb.files
      uses: std.FileSet
      with: { type: systemVerilogSource, include: "*.sv" }
```

Two fragments can now both define `files` without colliding
(`top.rtl.files` vs `top.tb.files`).

**Important:** the namespace is exactly **one level deep**:
`<package>.<fragment-name>.<task>`. Naming a fragment that is itself nested
inside another named fragment does **not** stack the prefixes — a task in a
fragment named `tests` is always `top.tests.<task>`, regardless of how deeply
the file is nested. Choose fragment names that are unique within the package.

Without a `name:`, a fragment's tasks join the package namespace directly
(`top.<task>`), and task names must be unique across all such fragments.

## Nested fragments

Fragments may include other fragments, letting the directory tree mirror the
project structure:

```yaml
# top/flow.yaml
package:
  name: top
  fragments: [src/flow.yaml]

# top/src/flow.yaml
fragment:
  fragments: [rtl/flow.yaml, tb/flow.yaml]
```

(File nesting is independent of namespacing — see the note above.)

## Local vs qualified references

Within a package, reference a task by its short name; from another package (or
across namespaces) use the fully-qualified name:

```yaml
# same package / namespace
needs: [files]

# qualified (cross-namespace or cross-package)
needs: [top.rtl.files, top.tb.files]
```

When a fragment is namespaced, tasks in *other* namespaces must use the
qualified form to reach it.

## Co-location principle

Define a task in the same `flow.yaml` as the files it describes; use fragments
to stitch directories together. Each task should declare only its **direct**
`needs` — let DFM resolve the rest. Verify the result with
`dfm graph <task> -o flow.dot`.
