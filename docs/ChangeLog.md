
# 1.19.0
- Add **`std.Publish` + `std.PubSet`** and a per-run **output-data directory**. Each `dfm run` has a designated output dir `rundir/out/<run-id>` (`<run-id>` is a zero-padded counter, or `--run-id <ID>` to pin it), with `rundir/out/latest` symlinked to the newest. `std.Publish` copies its consumed `std.FileSet`/`std.PubSet` files there under a path algebra (`dest` adds structure, signed `strip` rebases, `flatten` collapses to basename; the task `dest` composes as a base prefix in front of each PubSet's `dest`), writes a provenance manifest `.dfm-publish.json` (dest → publishing task, originating task, sha256, size), and detects conflicting overwrites (`on_conflict: error|warn|replace|skip`). `std.PubSet` binds a placement policy to a group of filesets so one `Publish` can place groups differently.
- Add **`dfm-out publish`** — the shell-task equivalent of `std.Publish`, copying files into `$DFM_OUT_DIR` with the same path algebra, provenance, and conflict handling. The runner exports `DFM_OUT_DIR`/`DFM_RUN_ID` to tasks.
- Materialize a **`rundir/bin`** with `dfm-out`/`dfm` shims that re-invoke the current interpreter and are placed on the task PATH, so shell tasks reach them without the console-script entry points being installed.
- Add the **`set:` block** for scoped subtree overrides: a list of assignment maps (rebind a scoped variable read via an ordinary `${{ pkg.var }}` reference) and/or scope items (`{uses?, path?, set: [...]}`) that narrow a rebind or force a parameter on matched descendants. Matchers: `uses:` (is-a over the node's `uses` chain) and `path:` (`*`/`**` globs). Precedence is *outer overrides inner*, with `-D` as the ceiling; `set:` overrides `with:`. Supersedes `let:`/`resolve()` (now deprecated but still working). hdlsim simulator selection is re-implemented on `set:` — the abstract tasks read `${{ hdlsim.sim }}`; select with `-D hdlsim.sim=<name>`, a subtree `set: [{ hdlsim.sim: <name> }]`, or a per-leg narrowed rebind.
- Fix `-D <pkg>.<name>=<value>` so it reaches ordinary `${{ pkg.var }}` reads (the override is now applied to the built package-params instance, not just the paramT default which pydantic v2 ignores at instantiation).
- Add **package maps** -- a generated `name -> flow file` manifest (`package-map:` key, `--package-map` flag, or `DV_FLOW_PACKAGE_MAP` env) that lets a project import dependencies by name without hard-coding paths. Maps register names lazily, so a dependency is parsed only when actually referenced. Multiple maps are supported (first-wins precedence).
- Import forms: import a package by `name` (located via map/registry), pin a name to an explicit file with `name`+`from`, and the `as:` alias is now honored -- an aliased import's tasks, types, and parameters resolve under the alias (e.g. `sim.SimImage`).
- Imports by name are loaded lazily: the dependency's flow file is parsed only when first referenced (unresolved names are still reported at load time). Building a task graph still materializes all reachable imports.
- Add `--report DIR` flag to `dfm run` -- writes a diagnostics bundle (per-task logs, markers, status as `report.json`/`report.md`/`markers.jsonl`) for publishing as a CI artifact. Assembled from each task's on-disk `exec_data.json`, so it is backend-agnostic (local, daemon, LSF). See the "Run Report Bundle" section of the command reference.
- `exec_data.json` now records each task's `markers` and `logfile` name (enables the backend-agnostic run report).
- Add Script ↔ Dataflow I/O contract for shell tasks: `DFM_*` env vars stage params/inputs/memento, and append-only files (`$DFM_OUTPUT`, `$DFM_ENV`, `$DFM_PATH`, `$DFM_MARKERS`, `$DFM_MEMENTO_OUT`) let scripts emit filesets, env, markers, and a memento downstream (GitHub-Actions-style). `TASK_SRCDIR`/`TASK_RUNDIR` retained as aliases.
- Add `dfm-out` helper CLI for emitting typed items/env/path/markers from shell tasks without hand-writing JSON
- Add template tasks (`template: true`) -- defer `run` expansion to graph-build time for reusable task definitions
- Add config-level task overrides (`overrides:` in configs) -- substitute arbitrary tasks when a config is active
- Add package-level task overrides (`overrides:` map on packages)
- Add `std.Null` no-op passthrough task for stubbing out tasks
- Add `--override TARGET=REPLACEMENT` CLI flag for ad-hoc task substitution
- Add `--runner` flag with auto-detect (daemon if running, else local)

# 1.11.0
- Support flow.yaml and flow.yml in addition to flow.dv
- Add support for loading package files relative to an environment variable
- Ensure tasks can be loaded from python modules relative to the flow.dv file
- Add similarity matching when a task is not found

# 1.10.0
- Refinements to support pytest and run environment variables

# 1.8.0
- Add support for '.needs' reference on tasks.  

# 1.7.0
- Enhance import in sub-projects to search root package first for relative paths
- Support for data-item emitting tasks

# 0.0.2
- Add support for compound tasks
- Add support for simple run-directory control
- Add control over input/output data-item passthrough

# 0.0.1
- Basic leaf-task functionality
