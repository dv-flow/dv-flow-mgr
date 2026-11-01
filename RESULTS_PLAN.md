# Run Results: implementation, test and docs plan

Design: [RESULTS_DESIGN.md](RESULTS_DESIGN.md) (section numbers below, like §4.2,
refer to it). This file is the tracker. Update the status table and the log at the
bottom as each work item finishes, so a fresh session can resume from this file
alone.

Repos (all under `packages/`): **mgr** = dv-flow-mgr, **hdlsim** =
dv-flow-libhdlsim, **proj** = dv-flow-libproject, **formal** = dv-flow-libformal,
**covsight**, and **ws** = the paper-support workspace (labs, wb-dma, docs).

## 0. Status

Legend: ☐ todo · ◐ in progress · ☑ done · ⏸ blocked (say on what)

| ID | Work item | Repo | Status | Notes |
|---|---|---|---|---|
| D | Record decisions Q1–Q6 (§0.1) | — | ◐ | Proceeding on the defaults; Q3 still open |
| 1.1 | Timestamp run-ids, eager `out/<run-id>`, `latest` | mgr | ☑ | Builder picks with `create=False` (see log) |
| 1.2 | `std.Result` family types + Python model/helpers | mgr | ☑ | `Check` → `std.ResultCheck` (name clash); see log |
| 1.3 | `dvflow-results/1` JSON Schema + `dfm util schema --results` | mgr | ☑ | Flow `$id` → `flow.dv.schema.json` |
| 1.4 | End-of-run recorder: synthesize, attach failures, write `results.json` | mgr | ☑ | |
| 1.5 | `dfm show results` | mgr | ☑ | + `--all`; `results/store.py`, `stale.py` |
| 1.6 | Fix `summary_builtin` exec_data filename | mgr | ☑ | Also the `result.*` nesting |
| 1.D | Docs for phase 1 | mgr | ☑ | Sphinx build clean |
| 2.1 | hdlsim `TestResult`/`SuiteResult` extend std | hdlsim | ☑ | Q4 default taken |
| 2.2 | Diagnostics mapping, `msg`, checks from the verdict table | hdlsim | ☑ | + UVM_ERROR lines as diagnostics |
| 2.3 | Role renames, `metrics` from `stats` | hdlsim | ☑ | |
| 2.4 | covsight reads the new `SuiteResult` shape | covsight | ☑ | Any std.Result tree |
| 2.D | Docs for phase 2 | hdlsim, covsight | ☑ | In `docs/index.rst` (Tasks.md is a stub) |
| 3.1 | Roll-up engine + metric registry | mgr | ☑ | Parity test vs sim_stats in hdlsim |
| 3.2 | `std.ResultCollect`; `std.TestSuite` emits `std.SuiteResult` | mgr | ☑ | + list-of-maps param bug fixed |
| 3.3 | JUnit / CTRF / markdown renderers in std | mgr | ☑ | |
| 3.4 | `test_summary` reads `std.Result` | mgr | ☑ | Via `SummaryCtxt.results` |
| 3.5 | `SimSuiteReport` shrinks onto std | hdlsim | ☑ | Intended diffs in log |
| 3.6 | `std.EvalSample` uses `std.TestResult`; evals CTRF | mgr | ☑ | EvalRunner implemented 2026-11-01 (log) |
| 3.D | Docs for phase 3 | mgr, hdlsim | ☑ | |
| 3b.1 | `FormalResult` in libformal | formal | ☑ | `uses: std.TestResult`; no per-property children |
| 3b.2 | `SynthResult` prototype (fixture library) | mgr tests | ☑ | Link-tree assert added with 4.1 |
| 4.1 | `results/` link tree + `FAILED/` | mgr | ☑ | |
| 4.2 | Artifact stamps + staleness in `show results` | mgr | ☑ | Landed with 1.5; tests here |
| 4.3 | Retention (`results.keep`) and `copy_logs` | mgr | ☑ | |
| 4.D | Docs for phase 4 | mgr | ☑ | |
| 5.1 | `notrun` entries for selected tests that produced no Result | mgr | ☑ | Plan on the runner node |
| 5.2 | libproject roots declare/produce Results; `run` check fix | proj | ☑ | Via hdlsim/std types (inherited produces) |
| 5.D | Docs for phase 5 | proj | ☑ | |
| 6.1 | Phase A: warn on roots without Result; `std.check.Produces` | mgr | ☑ | |
| 6.2 | `std.result.artifacts` helper; `SimCovMerge` + covsight use it | mgr, hdlsim, covsight | ☑ | covsight keeps its own (dv-flow-free) walk |
| 6.3 | Phase B: filter the root output port | mgr | ☑ | Only roots that declare a Result (see log) |
| 6.4 | Phase C: `results.strict_roots` | mgr | ◐ | Implemented; default stays off (libproject `lint-rtl`/`src-rtl`) |
| 6.D | Docs for phase 6 | mgr, proj | ☑ | |
| 7.1 | MCP `dfm_get_results` tool | mgr | ☑ | + agent tool; `mcp` not installed here |
| 7.2 | `task.result` events | mgr | ☑ | `run.end` sent after the record |
| 7.3 | VSCode results view | ext | ⏸ | Needs D(Q3) |
| 8 | Workspace docs: labs, wb-dma, slides point at results | ws | ⏸ | Lab/wb-dma files are being edited elsewhere; nothing committed yet (log) |

### 0.1 Decisions (defaults to proceed with)

These are the open questions from design §9. Each has a default so work can
start. Change the default here before the item that depends on it.

| Q | Default | Needed by |
|---|---|---|
| Q1 strictness | Filter the root output port to Result items (Phase B) | 6.3 |
| Q2 history | Keep shared task rundirs. Use mtime/size staleness, plus `copy_logs` (off by default) | 4.2, 4.3 |
| Q3 extension home | Open. Ask which extension `usage.py:88` refers to | 7.3 |
| Q4 `passed` clash | `passed` is a bool on every node; counts move to `counts.pass`. covsight changes in the same change set (2.4), and hdlsim adds a read-only `npassed` alias for one release | 2.1 |
| Q5 seeds | Out of scope. `seed` stays a field that producers fill in when they know it | — |
| Q6 profiles | `TestResult`/`SuiteResult`/`TestRunResult` live in std. Synth and formal types belong to their libraries. std ships a metric-name registry | 3.1, 3b |

Settled by the user's notes on the design (now in the doc):
- The run-id is a timestamp `YYYYMMDD-HHMMSS`, with a `-N` suffix if two runs land in the same second, and `out/latest` is kept up to date.
- The record is `out/<run-id>/results.json`, with a link tree at `out/<run-id>/results/`.

### 0.2 Conventions

- Run the mgr unit tests to a log:
  `cd packages/dv-flow-mgr && PYTHONPATH=$(pwd)/src ../python/bin/pytest -x tests/unit > /tmp/…/mgr-unit.log 2>&1; tail -30 …`.
  Use the scratchpad for logs.
- Run each lib's tests the same way from its own root (`tests/unit`, then
  `tests/system`).
- Every work item's done-when includes: the existing suite passes, the new tests
  pass, the docs listed for it are written, and this table is updated.
- Python code for results lives in a new package, `src/dv_flow/mgr/results/`, so
  std task modules (`std/*.py`) stay thin wrappers over it.
- Shared fixtures go in `tests/unit/data/results/`. They are hand-checked
  `results.json` files: test-suite pass, test-suite fail, build-failure,
  synth-timing-fail, formal-cex, a mixed root, and a legacy `report.json`. The
  schema test, the renderer tests and the extension's tests all read them, so they
  serve as the contract.

---

## Phase 1: core format and run record (mgr)

### 1.1 Timestamp run-ids

Change:
- `run_id.py`: rewrite `alloc_run_id(root_rundir, now=None)`:
  - Format `time.strftime("%Y%m%d-%H%M%S", localtime)`.
  - On a collision, add `-2`, `-3` and so on.
  - **Create** `out/<id>` with `os.mkdir` in a retry loop. That makes allocation
    atomic when two `dfm run`s start in the same rundir in the same second.
  - Allocation is now eager, because every run writes a record. Update the module
    docstring that says "a run that publishes nothing leaves no trace".
- Add `is_run_id(name)` (it matches the timestamp form *and* the legacy `\d{4}`
  form). Retention (4.3) and `show results --run` use it.
- `cmd_run.py:357` and `task_graph_builder.py:472` keep calling it. An explicit
  `--run-id` (`ci-42`) still wins and is used verbatim.
- `std/publish.py`: no logic change. It already symlinks `latest` atomically
  (`_atomic_symlink`). Move `_atomic_symlink` to `run_id.py` as `set_latest()`,
  so the recorder (1.4) and Publish share it. Fix the docstring at `:22`.

Tests (`tests/unit/test_run_id.py`, new):
- The format matches `^\d{8}-\d{6}(-\d+)?$`.
- Two allocations with a frozen `now` give `T` and `T-2`, and both dirs exist.
- Concurrency: 8 threads allocate with the same `now`, and all ids are distinct.
- `is_run_id` accepts the timestamp form, `0003` and `ci-42`. It rejects `latest`
  and `foo`.
- `set_latest` replaces an existing link atomically and works when `latest` is
  missing.

Update `tests/unit/test_publish.py`: its hard-coded `"0001"`/`"0002"` expectations
(lines 105-329) should resolve the id through `builder.run_id` or the `latest`
link rather than a literal. The ordering test at `:210` becomes "ids are distinct
and sort in creation order".

Done when: the publish tests pass with timestamp ids, and `DFM_OUT_DIR` points at
a directory that exists before the first task runs.

### 1.2 Types and the Python model

YAML (`std/flow.yaml`, `types:` near `:794`, next to `DataItem`/`FileSet`):
`Diagnostic`, `Metric`, `Check`, `Result`, `TaskResult`, `TestResult`,
`SuiteResult`, `TestRunResult`, exactly as in design §3.1/§3.4. Each gets a `doc:`.
Watch for the name clash: `std.TestSuite` is already both a task (`:586`) and a tag
type (`:729`). The new item type is `SuiteResult`, so it doesn't clash, but check
that `std.Test`/`std.TestSuite` tag lookups don't change.

Python (`src/dv_flow/mgr/results/`, new):

| Module | Contents |
|---|---|
| `model.py` | Pydantic models for the on-disk format: `Diagnostic`, `Metric`, `Check`, `Artifact` (a FileSet dump plus `mtime`/`size`/`stale`), `ResultNode` (recursive), `RunInfo`, `Summary`, `FailureEntry`, `ResultsFile` (`schema = "dvflow-results/1"`). They are the source of the JSON Schema. Use `extra="allow"` on `ResultNode`, so profile fields (`testname`, `seed`, hdlsim's `errors` …) are kept. |
| `status.py` | The status vocabulary and helpers: `STATUSES`, `is_ok(status)`, and `worst(a, b)` with the order error > timeout > fail > notrun > skip > pass. |
| `convert.py` | `to_node(item, type_resolver)`: turns a `std.Result` data item into a `ResultNode`. Recurses through `children`, fills `type`/`types` lineage, normalizes bare-number metrics to `Metric` and `passed` from `status`, maps the legacy `trace`→`waves` and `stats`→`data` roles, and caps diagnostics at N while keeping `counts` (design §3.1 rules). |
| `lineage.py` | `type_lineage(type_name)`: the `uses:` chain through the type registry, from the same data `type_match.is_a` uses. Put the shared walk in `type_match.py` rather than duplicating it. |
| `api.py` | Helpers for task authors: `mk_result(ctxt, type="std.Result", name=…, **kw)`, `metric(value, unit, better)`, `check(name, status, metric=, op=, goal=)`, `eval_check(metrics, name, metric, op, goal)` (it computes the status), `diagnostic_from_marker(m)`, `artifact(ctxt, path, role, filetype, label=)`, and `finish(result)`, which derives `status` from the checks, sets `passed` and fills `counts`. |

Tests:
- `tests/unit/test_results_types.py`: each new type loads, `mkDataItem("std.TestResult")` works, and `is_a(TestRunResult, Result)`, `is_a(SuiteResult, Result)` and `is_a(TestResult, Result)` all hold. Also a user package with `uses: std.Result` is is-a `std.Result`.
- `tests/unit/test_results_convert.py`:
  - lineage order;
  - a bare-number metric is normalized;
  - capping: 25 diagnostics give 10 kept, `counts` stays exact, and errors sort before warnings;
  - legacy role mapping;
  - unknown extra fields survive;
  - a nested child of another profile type keeps its own lineage.
- `tests/unit/test_results_api.py`:
  - `eval_check` for each op, including when the metric is missing (status `error`);
  - `finish()`: any failed check gives `fail`, all checks pass gives `pass`, and an explicit `error` is preserved.

### 1.3 JSON Schema

- `util/cmds/cmd_schema.py`: add `--results`, which emits
  `ResultsFile.model_json_schema()` with `$id` `https://dv-flow.github.io/dvflow-results.schema.json`.
- Check the generated file in at `share/dvflow-results.schema.json`, next to
  `share/dv.flow.schema.json`.
- While in that file, fix the appendix's `$id` mismatch for the flow schema
  (`cmd_schema.py:103`). The std YAMLs reference `flow.dv.schema.json`, so make the
  two agree. If that touches external URLs, record the choice in the log.

Tests (`tests/unit/test_results_schema.py`, the same pattern as
`test_schema_integrity.py`):
- The checked-in schema equals the generated one.
- Every fixture in `tests/unit/data/results/` validates (with `jsonschema`, which is
  already a dependency of `test_schema_validation.py`).
- A fixture with a wrong `status` value or a missing `schema` key fails to validate.

### 1.4 End-of-run recorder

New `results/recorder.py`: `ResultsRecorder(runner, root_nodes, rundir, run_id, argv, start_time)` with `record() -> ResultsFile | None`.

Steps (design §4.2):
1. **Pick the root Result.** Get the root node's output (`runner.run` returns it,
   `task_runner.py:332`, and `cmd_run.py:520` currently drops it; capture it). Keep
   the items that are `is_a(std.Result)`:
   - one item: use it;
   - several: wrap them in a `std.Result` named after the root, with those items as
     children;
   - none: synthesize (step 2).

   With several root tasks on the command line (`dfm run a b`), make one
   synthetic root per run with a child per root task.
2. **Synthesize a `std.TaskResult`** from a task node:
   - `status`: `pass` if the node's result status is 0, else `error`.
   - `msg`: the first error marker, else "exit status N".
   - `diagnostics`: from the markers.
   - `artifacts`: the output FileSets, with roles guessed from `filetype` by a
     table in `results/roles.py` (`*Log`→log, `*CovDb`→cov, `fst|vcd`→waves …,
     defaulting to `other`), plus the task's own log from
     `naming_scheme.log_filename` (`task_node.py:151`) as `role: log` if it exists.
   - `task` and `rundir`: from the node.
   - `start_time`/`end_time`: from the node's timing.
3. **Attach unaccounted failures.**
   - Walk the root's subgraph and collect the nodes that failed (non-zero status,
     not skipped).
   - A failure counts as *accounted* when some node in the Result tree has a `task`
     equal to it, or to a compound ancestor of it, or has a `rundir` under the
     failed node's rundir.
   - Add each unaccounted failure under the root as a `TaskResult` child in a
     `_tasks` group node.
   - If the root's status is `pass` while an unaccounted failure exists, raise it
     to `error` with `msg` "flow error: N task(s) failed outside any result". This
     keeps the record consistent with the run's exit status.
4. **Stamp the artifacts.** Record each file's `mtime`/`size`. Set `reused: true` on
   nodes whose producing task was up to date or a cache hit (check how
   `task_node` records that; it's the same flag `exec_data` gets).
5. **Compute the summary** (`results/summary.py`). Leaf `counts`, `failures[]` (the
   path from the root by `name`, the failing checks, the first `log` with the first
   diagnostic's line, and the first `waves`), `status`/`msg`/`metrics` copied from
   the root, and `metrics.walltime_s` from the run start and end.
6. **Write.** `results.json` (atomic: a temp file, then rename), then `summary.md`,
   then `set_latest(run_id)`. The tree comes in 4.1.

Wire it into `cmd_run.py`, after `asyncio.run(runner.run(tasks))` and before
`_emit_summary`:
- Wrap it in `try/except Exception`. On failure, log a warning ("could not write
  run results: …") and go on. Writing results never changes `runner.status`
  (design §4.2 step 5).
- Print one line after the summary: `Results: rundir/out/<id>/results.json`. Leave
  it out when the root's output is machine-formatted (`machine_output`, the
  `tests-info --json` case).
- `--no-results` turns the recorder off (an escape hatch for benchmarks).

`results.json` now covers the same ground as `--report-dir`. Leave that feature
alone for now, but record in the log whether it should later become a renderer of
the results record.

Tests (`tests/unit/test_results_record.py`). Each case is a tiny flow run through
the in-process runner, as the other runner tests do:
- **Result root:** a pytask root returns a `std.TestResult` with one failing
  check. `results.json` holds it, the summary has 1 failure with the check, the
  `latest` link is right, and the exit status is unchanged.
- **Non-result root:** a shell task root that exits 0 gives a `std.TaskResult` with
  status `pass` and its log artifact.
- **Build failure:** `build` (exit 1) feeds `test` (never runs). The result has a
  `_tasks/build` TaskResult with the error marker and its log. The summary status
  is `error`, and `failures` lists `build`.
- **Accounted failure:** a check task returns status 0 with a failing Result. No
  extra `_tasks` node appears.
- **Compound attribution:** a failure inside a compound whose Result names the
  compound is not attached twice.
- **Multiple roots:** `dfm run a b` gives a synthetic root with 2 children.
- **Resilience:** a root that outputs a malformed Result (status `"bogus"`) still
  gets a record. The node is written with status `error`, a warning is logged, and
  the run's exit status is unchanged. Monkeypatch the writer to raise, and the run
  still exits normally.
- **`--no-results`:** nothing is written.
- **Up to date:** run twice. The second record marks the nodes `reused: true`.

### 1.5 `dfm show results`

New `cmds/show/cmd_show_results.py`, registered in `__main__.py` with the other
`show` subcommands:
- `dfm show results [--rundir R] [--run ID|latest] [--failures] [--json] [--depth N] [--list]`.
- `--list` lists the records (id, root, status, counts) newest first.
- With no flags, it prints the console tree (status icon, name, msg, key metrics),
  collapsing passing subtrees.
- `--json` prints `results.json`. `--json --failures` prints only `.summary`.
- A missing record exits 1 with a hint ("no results under rundir/out; run `dfm run …`
  first").
- Build the text output in `results/render_text.py` so that 3.4 can reuse it.

Tests (`tests/unit/test_show_results.py`), against fixtures copied into a temp
rundir:
- `--list` ordering;
- `--run latest` versus an explicit id;
- `--json --failures` equals the fixture's `summary`;
- text output for a pass, a fail and a synth fixture (snapshot);
- a missing rundir.

### 1.6 Appendix fix

`summary_builtin._load_disk_result` (`summary_builtin.py:140`): find the file
through the naming scheme, as `task_listener_report.py:99` does. Add a regression
test to `tests/unit/test_task_summary.py`.

### 1.D Docs (phase 1)

| Doc | Change |
|---|---|
| `docs/reference/results.rst` (new) | Format reference: the file layout, each type and field, status semantics, lineage, capping, the summary block and how it is computed, artifact roles, and the JSON Schema location. Use the synth and test fixtures as worked examples. Add it to `docs/reference/index.rst`. |
| `docs/guide/running.rst` | New section, "Run results". Covers: where the record goes, `out/latest`, `dfm show results`, `--no-results`, and how a build failure shows up. |
| `docs/RundirLayout.md` | Rewrite to match the code: per-task dirs under `rundir/`, plus `out/<run-id>/{results.json,results/,summary.md}` and `out/latest`. Fixes the appendix finding. |
| `docs/reference/cli.rst` | `dfm show results`, `dfm run --no-results`, `dfm util schema --results`. |
| `docs/reference/stdlib.rst` / `guide/stdlib.rst` | The new std types. |
| `share/skills/dv-flow-manager/SKILL.md` + `references/` | After `dfm run`, read `rundir/out/latest/results.json` → `.summary` (or `dfm show results --json --failures`), then open the log at `failures[].log.line`. Remove any "search the rundir" advice. |
| `docs/ChangeLog.md` | Entry: results record, timestamp run-ids (a behavior change for anyone parsing `out/0001`). |

---

## Phase 2: libhdlsim on the std types (hdlsim, covsight)

### 2.1 Types extend std

- In `flow.dv` (`:1114-1365`), change `TestResult` to `uses: std.TestResult` and
  `SuiteResult` to `uses: std.SuiteResult`. Remove the fields std now owns. Keep
  the hdlsim extras (`errors`, `warnings`, `fatals`, `sim_errors`, `sim_fatals`,
  `assertion_failures`, `run_status`, `runinfo`).
- `SuiteResult.passed` becomes a bool (Q4). The count moves to `counts.pass`, and
  `npassed` is kept as an alias for one release.
- Check `SimRunResult`: if it is an intermediate item (sim ran, no verdict yet), it
  does **not** extend `std.Result`. Note this in its doc.

### 2.2 Diagnostics, msg, checks

- In `sim_check.py` (`SimCheck`, `SimUVMCheck`) and `SimUVMCase`, map the parsed
  messages to `Diagnostic`:
  - `log_line` → `loc.line`, and the log path → `loc.path`;
  - `file`/`line` → `src_loc`;
  - `category` is `uvm`|`sva`|`sim`.
- `msg` is the first error. This is the line `SimSuiteReport` prints today. Move
  that formatting into the check.
- Turn the verdict table (`uvm_log_parser.py:20-66`) into named `checks`:
  `uvm_errors == 0`, `uvm_fatals == 0`, `sim_errors == 0`, `assertions == 0`,
  `sim_exit == 0`, `test_done` (UVM report summary seen). Each check's metric is
  the matching count. The status comes from `api.finish()`, so the verdict and
  the checks can't disagree.
- Test: compare the verdict before and after the change on the existing
  `uvm_log_parser` corpus. Nothing should change.

### 2.3 Roles and metrics

- `vl_sim_runner.py:416-441` (and the other sims' runners that set roles; grep
  `role`): `trace`→`waves`, `stats`→`data`.
- Fill `metrics` from `sim_stats` with units and directions: `walltime_s` (s,
  lower), `simtime` (unit from the timescale), `maxrss_mb` (MB, lower), and
  `cov_*_pct` (%, higher) when coverage is on. `stats` stays as an alias for one
  release.

### 2.4 covsight

- `sources.py:73-91`: read case status from `status`/`passed` (bool), and suite
  counts from `counts` with a fallback to the old int `passed`/`total`. Read cov DBs
  through artifacts with `role: cov`. Keep the `filetype` fallback.
- Tests: the existing covsight dvflow tests, plus a fixture with the new shape and
  one with the legacy shape.

Tests (hdlsim): update `test_sim_check.py`, `test_sim_run_result.py`,
`test_sim_suite.py`, `test_sim_uvmcase.py` and `test_uvm_log_parser.py` for the new
shape, and add `test_result_shape.py`:
- every emitted case is a `std.TestResult`;
- the lineage includes `std.Result`;
- checks are named;
- each diagnostic has `loc.path`/`loc.line` pointing into the log;
- the roles are `log`/`waves`/`cov`/`data`.

Then run the mgr recorder over a real Verilator UVM pass/fail pair (a system test in
hdlsim `tests/system`), and check that `results.json` validates against the schema
and that `failures[0].log.line` is the `UVM_ERROR` line.

### 2.D Docs (phase 2)

- hdlsim `docs/Tasks.md`: result types, checks, roles and metrics tables.
- `docs/skill.md`: point at `results.json` rather than `report.json`.
- covsight docs: a note that it accepts `std.Result` trees.

---

## Phase 3: aggregation and renderers (mgr, hdlsim)

### 3.1 Roll-up engine and metric registry

- `results/rollup.py`: `rollup(children) -> (status, counts, metrics)`.
  - Status is the worst of the children.
  - Counts are leaf statuses, summed.
  - Metrics use the per-name rule from the registry: `sum` | `max` | `min` | `mean`
    | `none`. A metric not in the registry rolls up by `better` (lower→sum for
    times and counts, higher→min, which is the conservative choice), or not at all
    if `better` is `none`.
- `std/result_metrics.yaml`: the registry (Q6). It covers name, unit, `better`,
  `rollup` and label for the common names (`walltime_s`, `simtime`, `maxrss_mb`,
  `cov_line_pct`, `fmax_mhz`, `wns_ns`, `tns_ns`, `luts`, `ffs`, `cells`,
  `area_um2`, `power_mw`, `depth`, `proven`, …). `api.metric(name, value)` fills
  in the unit and direction from it.
- Match hdlsim's documented `_max`/`_mean` behavior in `SuiteResult.stats`, with a
  test that it matches the old output.

### 3.2 `std.ResultCollect` and `std.TestSuite`

- `std.ResultCollect` (a std task, `std/result_collect.py`, a thin wrapper over
  `rollup`):
  - Gathers the `is_a(std.Result)` inputs into one node.
  - Params: `name`, `type` (default `std.Result`), `checks` (for example
    `[{name: all_pass, metric: fail, op: "==", goal: 0}]`).
  - Leaves other inputs alone (doesn't pass them through), and lists that in its
    doc.
- `std.TestSuite` (`flow.yaml:586`) emits a `std.SuiteResult` through the same
  code. `std.TestRunner` (`:371`) wraps it in `std.TestRunResult`.

Tests (`test_result_collect.py`):
- mixed children (test + synth + TaskResult) roll up with the right status;
- counts are by leaf;
- metric rules work, including an unregistered metric and `better: none`;
- nested suites;
- empty input gives status `notrun` with msg "no results";
- non-Result inputs are ignored.

### 3.3 Renderers

`results/render_junit.py`, `render_ctrf.py` and `render_md.py`. They take a
`ResultsFile` and are pure, with no I/O:
- **JUnit:**
  - a test-profile node becomes a `testcase`, and a suite node a `testsuite`;
  - any other leaf becomes a `testsuite` with one `testcase` per check (so
    `synth/timing` fails in CI);
  - `failure` carries `msg` and the failing checks, and `system-out` the log path;
  - `error` and `timeout` become `<error>`; `skip` and `notrun` become
    `<skipped>`, with notrun's message naming the blocker.
- **CTRF:** the same mapping, following the CTRF spec version hdlsim uses today.
  `extra` carries the metrics.
- **Markdown:** `summary.md` (replaces the 1.4 placeholder).
- **Hookup:**
  - `dfm show results --format junit|ctrf|md [-o FILE]`;
  - config `results.formats: [junit, ctrf]` writes them next to `results.json`
    on every run;
  - an env/CLI override for CI (`--results-format junit`).

Tests:
- `test_render_junit.py`:
  - golden outputs for each fixture;
  - XML well-formed; testcase and failure counts match the summary;
  - a synth timing failure appears as a failed testcase named `timing`.
- `test_render_ctrf.py`: validated against a vendored minimal CTRF schema.
- **Parity:** feed hdlsim's existing JUnit test inputs through std. The testcase
  names, counts and failure messages match the old writer (the formatting may
  differ; record any intended differences).

### 3.4 Console summary

- `std/test_summary.py`: if the root output holds a `std.Result`, render it with
  `results/render_text.py`. Otherwise use the duck-typed path (`:44-71`), kept for
  one release with a deprecation debug log.
- `summary_builtin`: prefer the run's `results.json` when it exists, so the console
  and the record cannot disagree.
- Tests: `test_test_summary.py` gets parametrized cases for the new path and the
  legacy path. Snapshot the output for pass/fail/notrun/build-failure.

### 3.5 `SimSuiteReport` shrinks (hdlsim)

- Swap the hand-written roll-up and writers (`sim_check.py:421-656`) for std's
  `rollup` and renderers.
- Keep writing `report.json`, declare it in `produces:`, and add `"superseded_by":
  "results.json"`.
- Keep `junit.xml`/`ctrf.json` in the task rundir for one release, rendered by std.
- Test: the existing `test_sim_suite.py` passes unchanged, apart from intended
  differences recorded in 3.3.

### 3.6 Evals

- `std/evals.yaml`: `EvalSample uses: std.TestResult`.
- Map scores to `metrics` and thresholds to `checks`. The CTRF output the YAML
  promises now comes from 3.3.
- Tests: the existing eval tests pass, plus one that the evals root produces a
  `results.json` whose CTRF rendering has one test per sample.

### 3.D Docs (phase 3)

- `docs/reference/results.rst`: add the roll-up rules, the registry, and the
  renderer mappings (with the JUnit-for-non-tests rule).
- `docs/guide/running_tests.rst`: how suites roll up, CI integration
  (`results.formats`), and reading results.
- `docs/guide/developing_tasks.rst`: a new section, "Producing a Result", that
  walks through `results.api` with a minimal pytask example for a non-test domain
  (a lint task with a `warnings <= 0` check).
- `std/evals.yaml` doc text: correct the CTRF claim.

---

## Phase 3b: proof that the format is domain-neutral

### 3b.1 libformal `FormalResult`

- In libformal's flow YAML, add `FormalResult uses: std.Result`.
- `sby_bmc.py:149` and `vcf_analyze.py` emit it:
  - attrs `engine`, `mode`, `top`;
  - metrics `depth`, `proven`, `failed`, `unknown`, `covered`;
  - one check per property group, and a child per property when the tool lists
    them;
  - the counterexample trace becomes a `waves` artifact.
- Remove the dependence on `hdlsim.TestResult`.
- Tests: unit tests in `dv-flow-libformal/tests/unit` with captured SBY outputs
  (pass, cex, unknown), plus the `results.json` from a system run validated
  against the schema.
- Docs: `docs/sby_bmc.md` and `docs/Tasks.md`.

### 3b.2 Synthesis prototype

No synthesis library exists yet, and yosys may not be installed in CI. So:
- Add a fixture package at `tests/system/results_synth/` that defines
  `yosys.SynthResult uses: std.Result` and a pytask that parses **captured** yosys
  `stat -json` output and a nextpnr timing report (both checked in).
- The pytask makes stage children (synth, pnr) and turns its `fmax_mhz` and
  `max_luts` params into checks.
- If yosys is on PATH, the test also runs it for real on a small design;
  otherwise it skips that part.
- The test runs `dfm run synth` on the fixture and asserts:
  - `results.json` validates against the schema;
  - the summary has 1 failure with the `timing` check;
  - the JUnit output has a failed `timing` testcase;
  - `dfm show results` prints fmax/WNS with units;
  - the link tree has `results/synth/pnr/log`.
- A mixed root (`ResultCollect` over the tests fixture, synth and formal) renders
  one tree with one verdict.

Done when: no renderer or recorder code has a test- or synth-specific branch.
Grep for profile type names in `results/` and confirm that only the profile panels
and the JUnit testcase mapping mention them.

---

## Phase 4: link tree, staleness, retention (mgr)

### 4.1 Link tree

`results/tree.py`: `build_tree(results_file, out_dir)` creates
`out/<id>/results/`. The layout is design §5.2:
- **Directory names:** use the node `name`, sanitized (`/` → `_`, no leading `.`).
  Sibling collisions get `~2` and so on.
- **`STATUS` file:** `<status>: <msg>`, plus the failing checks one per line.
- **Links:**
  - artifacts link by role with the original basename: `log`, `waves.fst`,
    `cov/…`, `report-<label>`;
  - `rundir` links to the task rundir;
  - `FAILED/` holds relative links to every non-passing leaf, and to the
    `_tasks/*` nodes.
- **Link form:** links into task rundirs are absolute. Links inside the tree are
  relative, so copying `out/<id>` keeps its internal structure.
- **No symlink support** (`os.symlink` raises): write `LINKS.txt` per node with
  the paths, and log one warning.
- `--no-results-tree` and config `results.tree: false` turn it off.

Tests (`test_results_tree.py`):
- the layout for the fail fixture;
- the `FAILED/` contents;
- `STATUS` text;
- name sanitizing and collisions;
- relative internal links resolve after `out/<id>` is moved;
- the fallback when `os.symlink` is monkeypatched to raise;
- a 2,000-leaf fixture builds in under 2 s.

### 4.2 Staleness

- `show results`, and the tree's `STATUS`, compare the recorded artifact
  `mtime`/`size` with the current file. On a mismatch they mark the artifact
  `stale` (`[stale]` in text, `"stale": true` in `--json` output).
- `results.json` is never rewritten after the run.
- Tests: touch a log after recording, and it shows up as stale. A deleted file shows
  as `missing`.

### 4.3 Retention and `copy_logs`

- Config (`.dfm/config.yaml`, loaded through the existing project config in
  `runner_config.py:104`):

  ```yaml
  results:
    keep: 20
    copy_logs: false
    tree: true
    formats: []
    strict_roots: false
  ```

  Parse it in `results/config.py`.
- **Prune** after writing:
  - Remove the oldest `is_run_id` dirs beyond `keep`.
  - Never remove `latest`'s target or anything that isn't a run-id.
  - Note in the docs that this also removes those runs' `std.Publish` outputs,
    because they share `out/<run-id>`. Add `results.keep: 0` = never prune.
- **`copy_logs`:** copy the `role: log` artifacts into `out/<id>/logs/<path>`, and
  point the tree's `log` links at the copies.
- Tests:
  - retention with 25 records and `keep: 20`;
  - with legacy `0003` dirs present;
  - an explicit `--run-id ci-42` (not timestamp-sorted; sort by mtime);
  - `copy_logs` copies and relinks.

### 4.D Docs (phase 4)

- `docs/guide/running.rst`:
  - the link tree, with an `ls` walkthrough;
  - `FAILED/`;
  - staleness and when to use `copy_logs`;
  - retention.
- `docs/reference/results.rst`: the config keys.
- `docs/RundirLayout.md`: add `results/`.

---

## Phase 5: not-run tests and libproject (mgr, proj)

### 5.1 `notrun`

- Where `std.TestRunner` resolves its selection (`std/test_select.py`, used by
  `TestRunner`/`TestInfo`), make the selected test list available to the recorder:
  `name`, `suite path` and `task`.
- In recorder step 3, for each selected test with no Result node:
  - add a `std.TestResult` with status `notrun` under its suite path;
  - set `msg` to "blocked: <failed task>", with the blocking task found by walking
    the test task's `needs` to the first failed node.
- If nothing failed and a test still produced no Result, the status is `error` with
  "no result produced" (this is how the libproject `run` gap is caught).
- Tests:
  - a build failure blocks 2 of 3 tests: there are 2 `notrun` entries naming the
    build, and counts are pass 1 / notrun 2;
  - a test task with no check gives `error` "no result produced".

### 5.2 libproject

- `dv/flow.yaml:200-312`: `tests`, `smoke`, `coverage`, `profile` and `tests-info`
  declare `produces: [{type: std.Result}]` (or the specific subtype).
- `coverage` emits a `std.Result` with `cov_*_pct` metrics, a `coverage_goal`
  check (goal from a param, default off) and the merged DB as a `cov` artifact.
- `tests-info` emits a `TaskResult` with `tests-info.json` as a `report`. Keep its
  `--json` stdout behavior.
- `dv/uvm/utils/flow.yaml:255-284`: add `SimUVMCheck` to the `run` compound.
- Tests: the libproject unit tests, plus a system test on its example project:
  `dfm run tests` with one forced failure gives the right record, and `dfm run
  coverage` gives a Result with a cov artifact.

### 5.D Docs (phase 5)

- libproject `docs/guide`: what each root produces, and reading results.
- libproject `docs/reference`: the `produces:` of each root.
- `COVERAGE_DESIGN.md`: a note on the Result-based input (ahead of 6.2).

---

## Phase 6: the root-task restriction (mgr, hdlsim, covsight, proj)

### 6.1 Phase A: warn

- `std/checks.yaml` + `checks.py`: `std.check.Produces{type}`, next to
  `std.check.Needs`. `std.TestRunner` and the libproject roots declare it.
- `produces_eval.py` (`ProducesEvaluator`): a built-in rule that a `scope: root`
  task whose `produces:` has no is-a `std.Result` gets a warning marker. It shows
  in `dfm validate` and at graph build.
- Tests:
  - `test_cmd_validate.py`: a warning for a bare root, none for a compliant root;
  - the `Produces` check passes or fails on a type-checked output.

### 6.2 `std.result.artifacts`

- `results/api.py`: `artifacts(inputs, role=None, filetype=None)` walks the Result
  trees in `inputs` and returns their artifact FileSets. Each one gets
  `attributes.result_path` and `attributes.testname`/`seed`.
- hdlsim's `cov_merge.py` (`SimCovMerge`) uses it, falling back to direct
  FileSets. covsight's `cov_import.py:75` (`Import`) and `cov_merge.py:19` use it
  as well.
- Tests:
  - helper unit tests;
  - hdlsim `test_cov_merge.py` with Result inputs and with legacy FileSet inputs;
  - covsight `Import` with a Result tree keeps the test name on each DB.

### 6.3 Phase B: filter

- After the root's run, the root's output port passes only Result items to its
  dependants: in `task_graph_builder`, or where a node's output is handed on (find
  the exact point in task_node output propagation).
- `coverage needs: tests` keeps working through 6.2.
- Tests:
  - a dependant of a root sees only the Result;
  - the libproject `coverage` end-to-end still merges the DBs.

### 6.4 Phase C: strict

- `results.strict_roots: true` turns the 6.1 warning into an error. Flip the
  default once mgr std, hdlsim, formal and proj have no warnings. To check, run
  `dfm validate` on each package's example flows in CI.
- Tests: a bare root under strict errors in validate and at run, with the
  `srcinfo` location.

### 6.D Docs (phase 6)

- `docs/guide/tasks.rst` / `dataflow.rst`: the root-output rule, why it exists,
  and how to reach files through `result.artifacts`.
- `docs/ChangeLog.md`: entries for phases A, B and C.
- libproject guide: `coverage` reads Result artifacts.

---

## Phase 7: live and IDE consumers

### 7.1 MCP

- `cmds/agent/dfm_mcp_server.py` (`list_tools`, `:71`) and `dfm_tools.py`: add a
  `dfm_get_results` tool with args `rundir`, `run`, `failures_only`. It returns the
  same JSON as `show results --json`.
- Test: the existing MCP tool tests, with a new case over a fixture.

### 7.2 `task.result` events

- `task_listener_events.py`: when a task's output contains an `is_a(std.Result)`
  item, send `task.result` with the converted `ResultNode`, capped. `run.end`
  carries the `results.json` path.
- Tests: `test_event_sink.py` gets a case that a result event arrives with a
  schema-valid node and that `run.end` has the path.

### 7.3 VSCode results view (blocked on Q3)

The scope is design §5.4. Planned so it can start the moment Q3 is answered:
1. **Discovery:** watch `**/rundir/out/*/results.json`; records grouped by rundir;
   `latest` expanded.
2. **Tree view and generic panel:** checks, metrics, diagnostics and artifacts;
   actions to open the log at a line, reveal the rundir, and open waves (with a
   configurable command).
3. **Problems panel:** from diagnostics (`src_loc` preferred).
4. **Profile panels:** test (diagnostics + waves) and synth (metric table, stage
   timeline).
5. **Compare two records:** new and fixed failures, metric deltas colored by
   `better`.
6. **Live view:** from `task.result` events.

Tests: the extension's unit tests use mgr's `tests/unit/data/results/*.json`
fixtures (copied or vendored at a pinned version), plus a schema-version check.
Docs: the extension README, and a short section in `docs/guide/running.rst`.

---

## Phase 8: workspace docs (ws)

Do this after phases 4 and 5 land and the workspace's ivpm packages pick them up.

- `docs/lab1..4/walkthrough.md`: replace "open `rundir/<task>/sim.log` and grep
  `UVM_ERROR`" with `dfm show results`, then `rundir/out/latest/results/FAILED/`.
  Add one exercise step that reads `results.json` `.summary`.
- `example/wb-dma/README.md` (and its sub-READMEs that talk about results):
  same change. Per memory, wb-dma uses `flow.yaml` only, so don't touch the retired
  Makefile.
- `ci/docs.sh`: its captured dfm runs pick up the `Results:` line. Regenerate the
  captures, and add a check that each lab's run produces a schema-valid
  `results.json`.
- Slides/diagrams: one slide or diagram update if a lab slide shows rundir
  digging. List each slide changed in the log.

---

## Test strategy (summary)

| Level | What | Where |
|---|---|---|
| Unit | model, convert, lineage, api, rollup, summary, renderers, tree, retention, run-id | mgr `tests/unit/test_results_*.py`, `test_run_id.py`, `test_render_*.py` |
| Contract | Fixtures validate against the checked-in schema, and the schema equals the generated one | `test_results_schema.py`, reused by the extension |
| Integration (in-process) | Recorder on tiny flows: result root, non-result root, build failure, notrun, multi-root, resilience | `test_results_record.py` |
| Library | hdlsim/formal/proj/covsight emit and consume the std shape; legacy shapes still read | each repo's `tests/unit` |
| System | A real Verilator UVM pass/fail run; the synth fixture; a mixed root; libproject example roots | hdlsim `tests/system`, mgr `tests/system/results_synth`, proj system test |
| Parity | JUnit/CTRF from std vs the old hdlsim writers; the `SuiteResult.stats` roll-up vs the old one | 3.3, 3.1 |
| Workspace E2E | `dfm run tests` on wb-dma with an injected `UVM_ERROR` and a broken fw build. Expect `summary.failures` = 1 fail + N notrun naming fw-build, and `results/FAILED/` populated | manual checklist in 8, then `ci/docs.sh` |
| Performance | A 2,000-leaf record: recorder + tree under 2 s; `results.json` size reasonable with capping | `test_results_tree.py`, `test_results_record.py` |

## Risks

- **Timestamp run-ids break anything that parses `out/0001`.** Mitigation:
  `is_run_id` accepts both forms, plus a ChangeLog entry. The only known consumer
  is `test_publish.py`.
- **Pruning deletes publish outputs** (they share `out/<run-id>`). Mitigation:
  document it, and `keep: 0` disables pruning. If it becomes a problem, revisit
  whether publish should live in `out/<id>/publish/`.
- **Unaccounted-failure attribution** (1.4 step 3) may double-report under
  compound tasks with custom rundirs. Mitigation: the compound attribution test,
  plus matching on `task` before `rundir`.
- **Phase B filtering** could break unknown external flows that consume root
  FileSets. Mitigation: Phase A warnings ship for at least one release first; a
  per-task opt-out (`results.filter_roots: false`) is available.
- **Recorder failures must never fail a run.** Covered by the resilience tests.

## Log

Add a dated line for each item finished, each decision changed, and anything
deferred.

- 2026-10-31: Plan written. The user's notes on the design (timestamp run-ids,
  `results.json` + `results/`) are folded into RESULTS_DESIGN.md.
- 2026-10-31: 1.1 done. `alloc_run_id(root, now=None, create=True)` and
  `is_run_id`, `set_latest` in `run_id.py`; Publish uses `set_latest`.
  Deviation: `TaskGraphBuilder` (used by `show`, `validate`, tests) picks an id
  with `create=False`, so building a graph without running it leaves no
  `out/<id>`; `cmd_run` allocates with `create=True` (or `makedirs` for an
  explicit `--run-id`) and passes the id to the builder.
- 2026-10-31: 1.2 done. Types in `std/flow.yaml`; `results/{model,status,
  lineage,convert,api}.py` (+ a minimal `rollup.leaf_counts` and
  `registry.lookup`, completed in 3.1); `type_match.type_lineage` is the
  shared walk. Decisions: (a) the check item type is `std.ResultCheck`,
  because `std.Check` is already the graph-build requirement base type;
  (b) `goal` is declared `float` (no `any` keyword type exists; checks travel
  as maps in `checks: list`, so the type is documentation); (c) diagnostic
  totals in `counts` use plural keys (`errors`, `warnings`, `fatals`,
  `infos`, as hdlsim and sim_stats already do), so they don't collide with
  leaf-status counts (`error`, `fail` ...); (d) `ResultCheck` maps also carry
  the observed `value`; (e) convert maps the legacy hdlsim shapes too
  (`message`/`log_line`/`file`/`line` diagnostics, `results` as children,
  int `passed` kept as `npassed`); (f) artifacts on disk carry `role`,
  `label` and per-file `stamps` [{path, mtime, size}].
- 2026-10-31: 1.3 done. `results.model.results_json_schema()`, checked in at
  `src/dv_flow/mgr/share/dvflow-results.schema.json`; `dfm util schema
  --results` (both the `dfm util` and the `python -m dv_flow.mgr.util`
  parsers). Fixtures in `tests/unit/data/results/` are generated once by a
  script, then checked in and reviewed; `test_results_schema.py` also asserts
  each fixture's `summary` equals what `compute_summary` gives for its tree.
  Flow-schema `$id`: changed the generator to
  `https://dv-flow.github.io/flow.dv.schema.json`, the URL every std and
  library YAML header already names (nothing publishes either file today).
- 2026-10-31: 1.4 done. `results/{recorder,summary,roles,render_md}.py`;
  wired into `cmd_run` (`--no-results`, `Results: <path>` line, suppressed
  for `machine_output`). Notes: (a) the recorder is a runner *detail
  listener* (`skipped`, `uptodate`, `cache_hit` events), which is how it
  knows skipped and reused tasks; (b) a skipped root is `notrun` with
  `msg: "blocked: <task> failed"` (the 5.1 wording, done early); (c) a root
  raised to `error` by its `_tasks` keeps `own_status`, which counts and
  failures use, so the blocked root shows as notrun and the build as error;
  (d) `failures` also lists a non-passing parent that no non-passing child
  explains (a synth run's timing check with passing stages) -- found by the
  synth fixture; counts stay leaf-based and the count msg never reports
  fewer failures than are listed; (e) nodes in `results.json` omit empty
  containers and `reused: false`; (f) `dfm run` takes one task, so the
  multi-root case is tested through the in-process runner. `summary.md` is a
  first markdown renderer (`render_md.py`), refined in 3.3. `--report-dir`
  left alone; it should later become a renderer over `results.json` (its
  report.json/markers.jsonl duplicate the record).
- 2026-10-31: 1.6 done. `summary_builtin.load_exec_data`/`node_rundir`:
  finds `<name>.exec_data.json` via the naming scheme, handles str and list
  rundirs, and reads the verdict from `result.{status,markers}` (the old
  code also read top-level keys that the real file never has).
- 2026-10-31: 1.5 done. `cmds/show/cmd_show_results.py` over
  `results/store.py` (list/resolve/load records; MCP reuses it in 7.1) and
  `results/render_text.py` (tree, failures, list; snapshots in
  `tests/unit/data/results/text/`). Added `--all` (expand passing
  subtrees). The 4.2 staleness check landed here too (`results/stale.py`,
  applied by `show results` to text and `--json`), since the stamps are
  already recorded; 4.2 still owns the tree's `STATUS` part and its tests.
- 2026-10-31: 1.D done. New `docs/reference/results.rst` (in the reference
  toctree); "Run results" section in `docs/guide/running.rst`; a
  `Result types` section in `docs/guide/stdlib.rst` (the generated
  `reference/stdlib.rst` picks up the types itself); `docs/RundirLayout.md`
  rewritten to match the code; `cli.rst` (`--run-id` default, `--no-results`,
  `show results`, a new `Util Command` section for `schema --results`);
  dv-flow-manager skill `SKILL.md` + `references/cli.md` ("read the results,
  don't search the rundir"); ChangeLog. `sphinx-build` has no warnings from
  these pages. Mgr unit suite: 2124 passed (baseline 2022); tests/system,
  examples, integration: 208 passed.
- Phase 1 is complete. Nothing is committed yet (the user has not asked).
- 2026-10-31: Phase 2 done, on the Q4 default (bool `passed`, `counts.pass`,
  `npassed` alias, covsight in the same change set).
  - hdlsim `flow.dv`: `TestResult uses: std.TestResult`, `SuiteResult uses:
    std.SuiteResult` (extras kept; `results` kept beside `children`, `npassed`
    added). `SimRunResult` documented as not a Result.
  - `uvm_log_parser`: also returns `uvm_diagnostics` (the first 10
    UVM_ERROR/UVM_FATAL lines with log line, source file/line, hier, time,
    report ID) and `test_failed`. This is what lets `failures[].log.line` be
    the UVM_ERROR line; the verdict logic is unchanged.
  - `sim_check.mk_test_result` (shared by SimCheck, SimUVMCheck, SimUVMCase):
    `checks` from the verdict table (`verdict_checks`: uvm_errors,
    uvm_fatals, sim_errors, sim_fatals, assertions, sim_exit, test_done --
    sim_fatals added to the planned list), `msg` (`headline`), std
    `diagnostics` (categories uvm/sva/sim/tool), `metrics` with registry
    units, `counts`, `attrs`, `task`/`rundir` set explicitly (the item's
    `src` is still overwritten with the case name for de-dup, so `task`
    cannot come from `src`). Status is the parser's; `finish()` over the
    checks is proven to return it by `test_result_shape.py` over the whole
    log corpus at exit 0 and 1 (plus synthesized rows for the table cases
    the corpus lacks).
  - `SimSuiteReport` builds the SuiteResult via `mk_suite_result` (worst
    case status; `error`/"no tests ran" when empty). Its nonzero CI-gate
    status is accounted for by the SuiteResult's `task`, so no `_tasks`.
  - Roles: `simTrace` -> `waves`, `simStats` -> `data` (vl_sim_runner,
    xzm); readers select by filetype, prof-* roles unchanged.
  - mgr side: `std/test_summary.py` reads a roll-up's pass count from
    `counts.pass`/`npassed` (an int `passed` still works) -- the minimal
    part of 3.4 needed so the console count stays right. Added
    `TaskRunCtxt.name` (and `task_name`, set by the remote worker), used by
    `results.api.mk_result`. The metric registry
    (`std/result_metrics.yaml`, part of 3.1) landed here because hdlsim uses
    it.
  - covsight `sources.py`: walks any Result tree (`children` or `results`,
    any depth), cov DBs by `role=cov` or `simCovDb`.
  - Tests: hdlsim unit 623 passed (same as baseline; 6 asserts moved from
    int `passed` to `npassed`), new `tests/unit/test_result_shape.py` (9),
    new `tests/system/test_results_record.py` (real Verilator pass/fail
    pair: schema-valid record, `failures[0].log.line` is the UVM_ERROR line);
    covsight 120 passed (2 new); libformal unit 1 passed / 7 skipped.
    libproject unit: 51 passed, 1 failed -- `test_archetypes.py::
    test_profile_ranks_the_cases_tests_ran` fails identically with all repos
    stashed to HEAD, so it predates this work.
- 2026-10-31: Phase 3 done.
  - 3.1 `results/rollup.py`: `rollup()`, `rollup_metrics(detail=)`,
    `metric_rule()`; registry `std/result_metrics.yaml` (landed in phase 2).
    `detail=True` reproduces hdlsim's `<key>`/`_max`/`_mean`;
    `test_result_shape.py::test_rollup_parity_with_sim_stats` checks the
    registry's rule equals `sim_stats.STAT_KEYS` and the values equal
    `sim_stats.aggregate` for every shared key. hdlsim's
    `SuiteResult.stats` still comes from `sim_stats.aggregate` (it is an
    hdlsim extra, and covers keys the registry doesn't); `metrics` comes
    from std.
  - 3.2 `std/result_collect.py` (`collect()`, `ResultCollect`,
    `TestSuiteRun`, `TestRunnerRun`) over `results/collect.py`
    (`top_results`, `runtime_resolver`, `is_result`), which the recorder
    now shares. `std.TestSuite`/`std.TestRunner` got `run:` bodies and
    `consumes: all` (run-time `consumes:` matching is exact-string, so a
    `{type: std.Result}` pattern would miss subtypes); passthrough stays
    `all`. A suite with no Result members emits nothing (rather than a
    `notrun` node that would hide that plain tests passed);
    `ResultCollect` with none emits `notrun` "no results" as planned.
    Found and fixed a pre-existing mgr bug on the way:
    `TaskGraphBuilder._expandParam` turned each map in a list param into a
    one-key map per string value plus the map (`tests/unit/
    test_list_of_map_params.py`).
  - 3.3 `results/render_junit.py` (`cases`, `render_junit`, `ctrf_doc`),
    `render.py` dispatch, `config.py` (`results:` section, also used by 4.x;
    `DFM_RESULTS_FORMATS`), `dfm run --results-format`, `dfm show results
    --format/-o`. Test cases carry scalar `attrs` + metric values as JUnit
    `<properties>` (with units) / CTRF `extra`, which is what kept hdlsim's
    seed/sim/coverage handles. Goldens in `tests/unit/data/results/junit/`;
    CTRF validated against a vendored minimal schema
    (`tests/unit/data/ctrf-schema-min.json`).
  - 3.4 `SummaryCtxt.results` loads this run's record (the recorder runs
    before the summary); `test_summary` renders from it when it holds test
    results, else the duck-typed path (debug log). `summary_builtin` was not
    changed: it is the per-task panel, which the record does not duplicate,
    and the `Results:` line follows it.
  - 3.5 hdlsim `SimSuiteReport`: junit.xml/ctrf.json rendered by std
    (`suite_record`, `_legacy_case_fill` for TestResults built without the
    std fields); `report.json` gets `"superseded_by": "results.json"` and is
    declared in `produces:`. It also consumes `std.SuiteResult`, so its
    `children` keep the wb-dma `std.TestSuite` tree (otherwise the record
    would hold the collectors' suites next to a flat copy of the cases).
    Intended differences from the old writers (tests updated): JUnit root is
    `<testsuites>` with one `<testsuite>` per suite path; the failure
    message is `<status>: <headline>` and the failing checks are its text
    (was a counts string); CTRF reproduction handles moved from `message`
    to `extra`, and `extra.simtime` is the number (608.0) rather than the
    string. Parity otherwise: testcase names, tests/failures/errors counts,
    the fail/error/timeout distinction, seed/sim/cov properties.
  - 3.6 `EvalSample uses: std.TestResult` (its own `passed`/`status`
    removed), `eval_sample.sample_result()`; the evals.yaml CTRF claims now
    point at the record's rendering. Deferred, pre-existing:
    `std.EvalRunner` cannot elaborate at HEAD -- `eval_select` imports
    `plan_need` from `test_select`, which no longer exists -- and
    `eval_log`/`eval_sample` are still `NotImplementedError` stubs; the
    evals test drives graded cases through `std.TestRunner`.
  - Tests: mgr unit 2181 passed; hdlsim unit+system 633 passed.
- 2026-10-31: Phase 3b done.
  - 3b.1 libformal: `formal.FormalResult` in `flow.dv` and
    `formal_result.py` (`parse_sby_log`, `mk_formal_result`); emitted by
    `formal.sby.Case` (replacing the borrowed `hdlsim.TestResult`;
    `formal.sby` now imports `formal`, not `hdlsim`) and by
    `formal.vcf.Run` (the VCF verdict is in `vcf_run.py`; `vcf_analyze.py`
    only compiles, so nothing to do there). Two deviations from the plan:
    (a) `FormalResult uses: std.TestResult` (design said `std.Result`) so a
    proof is a test case to std suites, the console report and JUnit -- it
    is still is-a `std.Result`; (b) no child per property: a proof is one
    case, and children would make leaf counts count properties as tests;
    properties are diagnostics (log line + source line) and metrics.
    Captured SBY outputs in `tests/unit/data/sby_runs/` (pass, cex,
    unknown, cover_unreached); `tests/unit/test_formal_result.py` (15 with
    the existing; sby is not installed here, so the 7 real-sby tests
    skip, and the "results.json from a system run" check is unrun for the
    same reason). Docs: `docs/sby_bmc.md` (Case + FormalResult),
    `docs/Tasks.md`.
  - 3b.2 `tests/system/results_synth/` (package `yosys`: `SynthResult`,
    a stand-in `FormalResult`, `synth` parsing captured yosys `stat -json`
    and a nextpnr log into synth/pnr stage children with `timing`/`area`
    checks; `regress` = `std.ResultCollect` over tests + synth + formal) and
    `tests/system/test_results_synth.py`: schema-valid record, one failure
    with the `timing` check, failed `timing` JUnit testcase, `show results`
    prints fmax/WNS with units, mixed root gives one tree and one verdict,
    and a guard that `results/` code (identifiers and non-docstring
    literals) never names a synthesis/formal/simulator type and names the
    test profile only in `render_junit.py`/`lineage.py`. The real-yosys
    variant skips (yosys not installed). The `results/synth/pnr/log`
    link-tree assertion is added with 4.1. Found while doing this: the
    console showed the first 4 metrics, which hid `wns_ns`; it now shows the
    metrics the node's checks read first (snapshots regenerated).

- 2026-10-31: Phase 4 done. `results/tree.py` (`build_tree`), `results/
  retention.py` (`prune`, `copy_logs`), wired into the recorder's `write`
  (formats -> copy_logs -> tree -> `latest` -> prune); `--no-results-tree`.
  Choices: reserved node names (`FAILED`, `STATUS`, `LINKS.txt`, `rundir`,
  `log`) get a `_` prefix so a child dir never collides with a link;
  `FAILED/` entries use the node's name (a name may contain `/`); a second
  log of a node is `log-<file>`, other roles `<role>-<file>`; the tree is
  rebuilt from scratch when a `--run-id` is reused. The `STATUS` file is
  written when the run ends, so it is never stale; staleness is a reader's
  job (`show results`, `SummaryCtxt.results`). Retention counts only
  `is_run_id` dirs (so `ci-42` neither counts toward `keep` nor is
  removed), sorted by the record's mtime. Tests: `tests/unit/
  test_results_tree.py` (layout, FAILED/, STATUS, sanitizing/collisions,
  move, no-symlink fallback, 2,000-leaf tree and record each < 2 s,
  staleness ok/stale/missing with the record unchanged, copy_logs,
  retention with 25 records, legacy `0003`, `ci-42`, `latest`), and the
  synth system test now checks `results/synth/pnr/log`. Mgr unit+system:
  2204 passed.
- 2026-10-31: Phase 5 done.
  - 5.1 `TestSelect` attaches a `TestPlan` (tree, resolution, test_key;
    `runs(root)` = [(test path, run nodes)] via the existing `run_nodes`)
    to the runner node. The recorder (`_plan_result`) completes a runner
    root's Result: a selected test with no Result node (matched by `task`
    == a run node, or a subtask of one) becomes a `std.TestResult` under its
    suite path -- `notrun` "blocked: <first failed task in its needs>", or
    `error` "no result produced" when nothing it needs failed. When the
    runner itself was skipped (a build failed), the root is built from the
    plan as a `std.TestRunResult`, collecting each test's own Results from
    its run nodes -- so a build failure shows "1 passed, 2 not run" and the
    build under `_tasks`, not a single notrun root. A skipped root's
    passthrough items are no longer taken as its Result. Tests:
    `tests/unit/test_results_notrun.py`.
  - 5.2 The roots inherit `produces:` (nearest declaration wins), so the
    Result types are declared where the work is: `hdlsim.SimCovMergeResult`
    and `hdlsim.SimProfReportResult` now `uses: std.Result` and are filled
    by `cov_merge.py` / `prof_report.py` (coverage: `cov_*_pct` metrics,
    merged DB `role=cov` + merge.log `role=log`, new `goal`/`goal_metric`
    params for a `coverage_goal` check; profile: run counts, CPU, report
    artifacts); `std.TestInfo` emits a `std.TaskResult` with
    `tests-info.json` as a `report` and declares it (`SimSuiteInfo`'s
    `produces: []` replaced). `tests`/`smoke` already produce
    `hdlsim.SuiteResult`. libproject `run` compound: `sim-run` in `mode:
    test` + a `check` (`hdlsim.SimUVMCheck`, `rundir: inherit`). Found:
    `results.api.artifact(None, ...)` passed `src=None`, which FileSet
    rejects -- fixed, with a test. Tests: libproject `test_archetypes.py`
    gains run-record assertions on `coverage` and a new
    `test_tests_records_a_failing_case` (real Verilator: suite root, 2
    cases, `failures` = the failing case with its sim error as headline and
    a log line). Wart noted, not changed: a `SimCheck` with no `name` param
    names its case after its rundir (`leaf.b`), so the record path is
    `tests/leaf.b`, not the `std.Test` name. libproject: 52 passed, 1
    pre-existing failure (`test_profile_ranks_the_cases_tests_ran`).
  - 5.D libproject `docs/guide/slots.rst` ("What each verb reports"),
    `docs/reference/project_dv.rst` (root produces table),
    `COVERAGE_DESIGN.md` note. Sphinx build clean for those pages.
- 2026-10-31: Phase 6 done except flipping the 6.4 default.
  - 6.1 `results/rootcheck.py` (`root_problem`, `produces_result`,
    `declared_produces`: the nearest non-empty `produces:` along the
    `uses:` chain -- an `override:` alias carries an empty list), used by
    `dfm validate` (`RootWithoutResult` warning, error under
    `strict_roots`, with srcinfo), by `cmd_run._check_roots` at graph build
    (a warning marker with the task's location; an error that stops the
    run under `strict_roots`) and by the new `std.check.Produces{type}`
    (`std/checks.yaml`, `checks.produces`; it reads the task's declaration,
    not the built node, so `--build-only`'s variant node passes).
    `std.TestRunner` declares `produces: [std.TestRunResult]` and
    `requires: [std.check.Produces]`; `std.TestSuite` `produces:
    [std.SuiteResult]`; `std.TestInfo` `produces: [std.TaskResult]`;
    libproject `coverage`/`profile`/`tests-info` declare the check (`tests`/
    `smoke` inherit it). The "ProducesEvaluator built-in rule" of the plan
    is this shared predicate rather than code in `ProducesEvaluator` (which
    only evaluates `${{ }}` in patterns). Tests: `test_root_results.py`,
    `test_cmd_validate.py` (2 new).
  - 6.2 `results.api.artifacts(inputs, role=, filetype=)`; hdlsim
    `cov_merge.collect_cov_sources`/`collect_cov_dbs` use it for any Result
    item (legacy type-named items and bare FileSets still read directly),
    and `SimCovMerge` also consumes `std.SuiteResult`/`std.TestRunResult`.
    covsight is deliberately free of dv-flow imports (its `sources.py`
    docstring), and its own walk already reads any Result tree with the
    case identity (2.4), so it does not call the mgr helper. Tests: mgr
    `test_results_api.py`, hdlsim `test_cov_merge.py::
    test_collect_from_a_std_result_tree`, covsight 2.4 tests.
  - 6.3 Deviation, for safety: only a root that *declares* a Result has its
    port filtered (Results + `std.Env` + `std.TaskFailure`); a root that
    declares none is passed through unfiltered. Filtering every root, as
    planned, would starve real dependants the design's survey missed --
    libproject's `src-rtl` is a root producing FileSets that `img` needs.
    Implemented in `TaskSetRunner._filter_root_port` at both completion
    points (run and base-rundir hit), `results.filter_roots: false` opts
    out (`cmd_run` sets `runner.filter_root_outputs`). `SimSuiteReport`
    now lists `report.json`/`junit.xml`/`ctrf.json` as the SuiteResult's
    artifacts so they stay reachable. libproject `coverage needs: tests`
    still merges (its archetype tests pass). Tests: `test_root_results.py`
    (dependant sees only the Result and reaches the log through it;
    non-compliant root unfiltered; opt-out).
  - 6.4 `results.strict_roots` works (validate and run, with location).
    The default stays `false`: `dfm validate` on wb-dma still warns for
    `gen` (a project codegen root) and `lint-rtl` (a libproject interface
    slot that produces FileSets), so the libraries do not all comply yet.
    Flipping it is a decision for when libproject's `src-rtl`/`lint-rtl`
    slots declare Results.
  - 6.D `docs/guide/dataflow.rst` ("Root Tasks Produce a Result"),
    ChangeLog, libproject `docs/guide/slots.rst`, skill line.
  - Suites: mgr 2219, hdlsim 635, libformal 15 (+7 sby skips), covsight
    120, libproject 52 (+1 pre-existing failure).
- 2026-10-31: 7.1 and 7.2 done; 7.3 still blocked on Q3.
  - 7.1 `results.store.results_json()` (exactly `show results --json
    [--failures]`, staleness marked); `dfm_get_results` in the MCP server
    (`list_tools` + `_dispatch` -> `get_results`, rundir defaulting to the
    session builder's) and in `dfm_tools.build_dfm_tools` for the agent.
    `tests/unit/test_mcp_results.py` tests the dispatch; the `mcp` package
    is not installed in this venv, so `build_dfm_mcp_server` itself can't
    be exercised here.
  - 7.2 `TaskListenerEvents._results`: a `task.result` event per std.Result
    a task itself produced (passthrough items are not repeated), as a
    run-record node with capped diagnostics. `run.end` gains `results`
    (the record's path): `dfm run` now creates the listener with
    `defer_end=True` and sends `run.end` itself after the recorder has
    written, so a consumer that reloads on `run.end` finds the file (on an
    exception, `run.end` is still sent from the except path). Test in
    `test_event_sink.py` (the node validates against the schema's
    `ResultNode`).
- 2026-10-31: Stopped before phase 8. The files it edits
  (`docs/lab1..4/walkthrough.md`, `example/wb-dma/README.md` and
  sub-READMEs, slides) gained uncommitted changes from someone else during
  this session (lab walkthroughs at 20:02-20:04), and the plan gates phase 8
  on phases 4-5 landing; none of this work is committed. Resume phase 8 once
  those edits are settled and the user says the package changes may be
  committed. Note: the workspace uses these packages live (ivpm), so lab and
  wb-dma runs already write `rundir/out/<id>/results.json` and print
  `Results: ...`; `dfm validate` on wb-dma warns for `gen` and `lint-rtl`.
  `ci/docs.sh`'s captured-output greps (`pss-lab3`, `SOC: PASS`) are
  unaffected by the extra lines.

### 2026-11-01: std.EvalRunner implemented (follow-up to 3.6)

The eval subsystem was a skeleton, not just a bad import: `EvalSelect`, all of
`eval_log` and most of `eval_sample` raised `NotImplementedError`. Now:

- `std/eval_select.py`: `EvalSelect` runs `TestSelect`, then builds each
  selected `std.Eval` case as `epochs` trial nodes (`<case>.e<N>`; bare name
  at epochs=1), swaps them in for the original's need edges, and marks every
  eval trial (and its body) `uptodate = False`. `epoch` is passed as the
  case's param when it declares one. `EvalPlan` (a `TestPlan`) reports a
  replicated case's trials to the recorder; `node.eval_trials` maps trial
  node -> (case path, epoch, benchmark, sample_id, view). Matrix-cell eval
  cases with `epochs > 1` are an error (not replicated yet).
- `std/eval_log.py`: `EvalRunnerRun` (the root's `run:`) stamps samples with
  epoch/id, reduces each replicated case to a `std.EvalCase` (verdict =
  reducer over trial verdicts, passing at 0.5; missing trials count as
  failed; `score_<name>` reduced too; trials listed in `trials`, not held as
  children), rewrites suite results in place, emits the `TestRunResult`, and
  writes the Inspect eval set (one `EvalLog` per benchmark x view, Inspect's
  `{timestamp}_{task}_{id}.json` naming, `eval_set_id` = run-id, old logs in
  the directory removed). A write failure (mixed models, `log_format: eval`
  without the `inspect` CLI) fails the root with an `eval_log` error check.
  `eval_summary` = the test report plus an "Eval logs:" line.
- `std/eval_sample.py`: `write_sample`, `sample_to_inspect` (transcript goes
  in `metadata`, not Inspect `events`), `read_trajectory` (JSON or JSONL),
  `score_value`, `trial_passed`.
- `evals.yaml`: EvalRunner `run:` body; new `std.EvalCase` type.
  `result_metrics.yaml`: `score_*`/`verdict` roll up by mean,
  `trials_passed` by sum.
- `results/collect.py`: `top_results` also treats samples a case lists in
  `trials` (by task + type) as held, so trials are not top-level results.
- Core fixes found on the way: `BuilderElabCtxt.mkTaskNode(task, **params)`
  now applies the params (they were rejected for the Task form); the base
  data-item `seq` default is `-1` (was `""` on an `int` field, which raised
  pydantic serializer warnings once a fresh item was nested in another).
- Docs: guide/running_tests.rst "Evals: graded cases and trials", stdlib.rst
  row, ChangeLog.
- Verified with Inspect itself: in a scratch venv with `inspect-ai` 0.3.287,
  `list_eval_logs()` finds the log and `read_eval_log()` validates it
  (`test_log_validates_with_inspect`, skipped where `inspect_ai` is absent).
- Tests: `tests/unit/test_eval_results.py` (23 + 1 skip). mgr unit+system
  2245 passed; hdlsim 640 (+1 timing-flaky `test_vlt_time` under load, passes
  alone); libproject 52 + the pre-existing failure.
- Not done: replicating matrix-cell eval cases; converting trajectories to
  Inspect `events`.

### 2026-11-01: link tree flattened

User feedback: `results/tests/uvm-tests/two-ch/` held only a `rundir` link,
an extra level; same for compound/suite nodes (`uvm-tests/rundir/<task>.exec_data.json`).
`results/tree.py` now links every run-directory entry of every node into the
node's directory under its own name (dotfiles and `STATUS`/`LINKS.txt`
excluded; a child's directory beats a same-named entry). Role aliases whose
target is already linked by name are dropped, except `log`; `rundir` is
linked only when the run directory no longer exists, and in the no-symlink
`LINKS.txt` fallback. Consequence: anything that walks all of `rundir/`
sees the task logs twice through `out/<id>/results/`; three mgr test helpers
and one libproject glob now skip it. Tests: `test_leaf_links_its_rundir_entries`;
mgr unit+system 2246 passed; libproject 52 + the pre-existing failure.
Docs: guide/running.rst, RundirLayout.md, ChangeLog.

### 2026-11-01: retention is `keep_previous`, default 1

User feedback: 20 records is more history than is useful. `results.keep`
(a total, default 20, `0` = never) is replaced by `results.keep_previous`
(earlier runs kept besides the current one, default 1; `0` = only this run,
`all` = never prune). Run dirs named with `--run-id` and `latest`'s target
are still never pruned and no longer count toward the limit. A config that
still says `keep: N` warns and reads as `keep_previous: N-1` (`keep: 0` as
`all`). Tests: `test_retention_default_keeps_one_previous`,
`test_config_keep_previous`. Docs: running.rst, reference/results.rst,
RundirLayout.md, ChangeLog.

### 2026-11-01: no empty FAILED/

User feedback: omit `FAILED/` when it would be empty. `results/tree.py`
creates it only when a summary failure resolves to a tree directory. Test:
`test_no_failed_dir_when_nothing_failed`. Docs: running.rst,
RundirLayout.md, ChangeLog.

### Where things stand (for a fresh session)

Done: phases 1-6 (6.4's default flip deliberately not done), 7.1, 7.2.
Open: 7.3 (Q3: which VSCode extension), 8 (see above), 6.4 default flip
(needs libproject `src-rtl`/`lint-rtl` and project codegen roots to declare
Results), and the deferred items in the log (the `leaf.b` case naming wart;
EvalRunner is done, 2026-11-01, except matrix-cell trials). Changed repos, all uncommitted:
dv-flow-mgr, dv-flow-libhdlsim, dv-flow-libproject, dv-flow-libformal,
covsight. Last full runs: mgr unit+system 2246 passed (2026-11-01); hdlsim unit +
results system test 635; libformal 15 (+7 sby skips); covsight 120;
libproject 52 + 1 pre-existing failure.

