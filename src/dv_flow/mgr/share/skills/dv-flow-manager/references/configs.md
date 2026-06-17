# Configurations & Parameters

## Parameters

Packages and tasks declare parameters under `with:`. Each parameter has a type
and optional default:

```yaml
package:
  name: top
  with:
    top_module:
      type: str
      value: "top"
    opt_level:
      type: int
      value: 0
```

Reference a parameter inside an expression by its **bare name**:

```yaml
with:
  msg: "Building ${{ top_module }} at -O${{ opt_level }}"
```

Override a parameter at the command line:

```bash
dfm run build -D top_module=core -D opt_level=2
```

A `-D` value can target a fully-qualified task parameter
(e.g. `-D top.build.opt_level=2`).

## append / prepend for list parameters

When a task `uses:` a base task (or otherwise overrides a list parameter), use
`append`/`prepend` to extend rather than replace the base value:

```yaml
with:
  args:
    append: ["-extra-flag"]      # added after the base value
  incdirs:
    prepend: ["/priority/inc"]   # added before the base value
```

Resolution order: `prepend + (value or base_value) + append`. If `value` is also
set, it replaces the base before prepend/append are applied. (Note: the merged
value is what the task implementation receives; do not rely on `append` results
being visible through an inline-shell `${{ }}` echo.)

For path-style variables there are also `path-append` / `path-prepend` (joined
with the OS path separator) — see `std.SetEnv`.

## Configurations

A **configuration** customizes a package for a scenario (debug/release,
tool/vendor, regression) without duplicating the package. Define them under
`configs:` and select with `-c`:

```yaml
package:
  name: top
  with:
    debug: { type: bool, value: false }
  tasks:
    - root: build
      shell: bash
      run: |
        echo "build (debug=${{ debug }})"

  configs:
    - name: debug
      with:
        debug: { value: true }
      tasks:
        - local: debug_args
          uses: std.Message
          with: { msg: "+define+DEBUG" }
          feeds: [top.build]      # inject into build only under -c debug
```

```bash
dfm run build -c debug
```

A configuration may specify:

- `with` — parameter values for this configuration
- `uses` — a base configuration to inherit from
- `overrides` — package/parameter overrides
- `extensions` — task extensions
- `tasks` — additional or overriding tasks
- `types`, `imports`, `fragments` — additional definitions

When a config is selected, DFM loads the base package, applies the config's
params/overrides, merges its tasks/types/imports/fragments, then builds the
graph.

**Prefer `feeds` + new tasks** in a config to inject behavior. (A config-level
`override:` of a task requires a `uses:` base package; for in-package tweaks,
adding a `feeds` task is the robust pattern.)

## Common config uses

- Build variants: `debug`, `release`, `profile`.
- Tool selection: switch simulator/vendor via `overrides`.
- Target platforms or test modes: normal vs. regression vs. CI.
