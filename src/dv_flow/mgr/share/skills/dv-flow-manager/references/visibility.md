# Task Visibility

Visibility controls which tasks are executable entry points, which are visible
across package boundaries, and which are internal implementation details.
**Default to hiding tasks** and expose a small, deliberate API.

## Scopes

| Scope | Behavior |
|---|---|
| `root` | Executable entry point. Listed when you run `dfm run` with no arguments. |
| `export` | Visible outside the package; other packages may reference it in `needs`. |
| `local` | Visible only within its declaring fragment (or a compound task body). |
| *(none)* | Package-visible only. Referenceable by tasks in the same package; warns if referenced from another package. |

## Specifying scope

Two equivalent ways:

### Inline markers (preferred)

Use `root:`, `export:`, or `local:` in place of `name:` to name the task and set
its scope at once:

```yaml
tasks:
  - root: build          # name: build  + scope: root
    run: make build
  - export: compile      # name: compile + scope: export
    run: ./compile.sh
  - local: helper        # name: helper  + scope: local
    run: echo internal
```

### The `scope` field

```yaml
tasks:
  - name: main
    scope: [root, export]   # both an entry point and a public API
    run: ./main.sh
```

Inline markers and `scope:` combine (e.g. `root: main` + `scope: export` =
both). **Only one** of `name` / `root` / `export` / `local` / `override` may be
used per task.

## Designing a package API

- Mark user-facing tasks `root` so they appear in the `dfm run` listing.
- Mark tasks that other packages should depend on `export`.
- Use `local` for helpers inside compound task bodies or config fragments.
- Leave everything else unscoped — internal wiring should not be part of your
  public surface.

This lets consumers see a clean set of entry points and exports while your
internal task graph stays free to change.
