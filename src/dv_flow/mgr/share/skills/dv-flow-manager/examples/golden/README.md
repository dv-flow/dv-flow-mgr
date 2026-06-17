# Golden example — idiomatic DFM project (std-only)

A complete, runnable project that demonstrates DFM best practices using only
`std.*` tasks, so it works with **no plugin packages installed**.

```
flow.yaml          # package: top  (root entry points, params, configs)
rtl/flow.yaml      # fragment name: rtl    -> top.rtl.files
tb/flow.yaml       # fragment name: tb     -> top.tb.files
tests/flow.yaml    # fragment name: tests  -> top.tests.smoke
rtl/top.sv, tb/tb_top.sv   # sample sources collected by the filesets
```

What it shows:

- **flow.yaml** everywhere; root `package:` + `fragment:` files.
- **Fragment hierarchy + namespaces** (`top.rtl.*`, `top.tb.*`, `top.tests.*`),
  co-located with sources.
- **Visibility**: `root` entry points (`build`, `smoke`), `export` filesets,
  `local` config helper.
- **Dataflow**: `needs` for direct deps; typed `produces`/`consumes`
  (`std.FileSet` → `buildManifest`).
- **Embedded shell + variables**: `shell: bash` + `run:` referencing
  `${{ top_module }}`, `${{ rundir }}`, `${{ defines }}` and `$TASK_SRCDIR`.
- **Configs**: a `debug` config that injects a task via `feeds`.
- **Parameters**: a package param (`top_module`) used in expressions.

Try it:

```bash
dfm validate                 # should pass
dfm show tasks               # top.build, top.rtl.files, top.tb.files, top.tests.smoke
dfm run top.tests.smoke      # build -> smoke
dfm run build -c debug       # debug variant (injects debug_defines via feeds)
dfm graph top.tests.smoke -o flow.dot
```
