# Run Results: a `std.Result` data-item format

Status: design proposal (2026-10-31). Scope: dv-flow-mgr (owner), dv-flow-libhdlsim,
dv-flow-libproject, dv-flow-libformal, a future synthesis library; consumers
covsight, CI, a VSCode extension, agents.

## 1. Problem

Every root run in a flow ends with the same three questions: did it succeed, what
went wrong and why, and where the evidence is. The answers change by domain, but
the questions don't:

| Run | Verdict | Key numbers | Evidence |
|---|---|---|---|
| `dfm run tests` | all cases pass | counts, sim time, coverage % | log at failing line, waves, cov DB |
| synthesis | completed, and timing/area goals met | WNS/TNS, fmax, cells/LUTs/FFs, power | log, timing/utilization reports, netlist |
| formal | properties proven/covered | depth, proven/cex/unknown counts | log, counterexample trace |
| lint, firmware build, docs, evals | clean / built | warning counts, image size, scores | log, report, image |

Today a user gets the verdict from the console and digs through `rundir/` for
everything else. The lab docs tell them to do exactly that
(`rundir/pss-lab2.single/sim.log`, grep for `UVM_ERROR`). Tests are the first and
most developed case, so most of the inventory below concerns tests. The format,
though, must not assume tests. The clearest evidence that it shouldn't is in
libformal: with no neutral type to use, its SBY task emits an `hdlsim.TestResult`
with `sim='sby'` (`dv-flow-libformal/.../sby_bmc.py:149`).

The data model is closer than it looks. Most of the pieces exist, but they sit in a
library, are found by duck typing, or are never written out at run level:

| What exists | Where | Gap |
|---|---|---|
| `TestResult` → `SuiteResult` per-case/roll-up items, with `artifacts` FileSets tagged `role=log/trace/cov/stats` | libhdlsim `flow.dv:1194-1316` | Library-specific. Any other producer (evals, formal, firmware, pytest) reinvents it |
| `std.test_summary` console report | mgr `std/test_summary.py:20-53` | Duck-typed: "has `passed` and no `total`" = case, "has `total`" = roll-up |
| `report.json` / `junit.xml` / `ctrf.json` | libhdlsim `sim_check.py:421-656` (`SimSuiteReport`) | A side file of one hdlsim task, not declared in `produces:`. Generic logic that lives in a library |
| `--report-dir` bundle (`dvflow-report/1`: report.json, markers.jsonl, summary.md) | mgr `task_listener_report.py` | Opt-in. Organized by task, not by test. Knows nothing about results |
| Root output | `runner.run` returns it (`task_runner.py:332`) | `cmd_run` discards it (`cmds/cmd_run.py:520`). Only the `summary:` hook sees it |
| Per-task `exec_data.json` with `output` | `task_node.py:337-397` | Correct but scattered: one file per task, mixed with params and commands |
| `rundir/out/<run-id>/` + `out/latest` | `run_id.py:30`, `std/publish.py` | Counter ids (`0001`), allocated lazily, only for publish. Unused by runs |
| `produces:` declarations | `task_def.py:433` | Static only (`dfm validate`). Nothing ties a root task to a kind of output |

The failures that matter most are also the ones the current results miss. If the
build fails, no `TestResult` is ever created. The suite says "no tests ran" and
the compile error sits as a marker on a task the user has to find. The same goes
for a lab `todo` gate, which fails outside any test.

## 2. Decision summary

1. **One domain-neutral format, many renderers.** Define `std.Result` in
   dv-flow-mgr's std library. It is a tree of nodes, each with a verdict, a
   headline, diagnostics, **metrics**, **checks** (metric-vs-goal criteria) and
   artifacts. Nothing in it is specific to tests. Each domain adds a thin subtype:
   `std.TestResult`/`std.SuiteResult` for tests, `SynthResult` in a synthesis
   library, `FormalResult` in libformal (§3.4). The symlink tree, the agent JSON
   summary, the console summary, JUnit/CTRF and a VSCode extension all render that
   one format. The format
   is the main decision. The two approaches in the question are views of it and do
   not compete.
2. **Every run records one Result tree.** At the end of every `dfm run`, dfm writes
   the root task's Result to `rundir/out/<run-id>/results.json`. If the root task
   didn't produce a Result, dfm makes one. Either way, dfm attaches every failed task
   in the subgraph that no Result accounts for (such as build failures).
   The run-id is a local timestamp, `YYYYMMDD-HHMMSS` (with `-2`, `-3` … on a
   same-second collision), and `out/latest` always links to the newest record.
3. **Root tasks output only a Result.** A `scope: root` task must declare
   `produces: [{type: std.Result}]` (an is-a match), and its output port carries only
   Result items. Downstream tasks reach files through `Result.artifacts`. This is
   enforced in stages: synthesize and warn first, error later (§6).
4. **Library result types extend the std ones.** `hdlsim.TestResult uses:
   std.TestResult`, and `hdlsim.SuiteResult uses: std.SuiteResult`. libformal gets
   its own `FormalResult uses: std.Result` instead of borrowing hdlsim's type.
   Existing field names stay, because covsight and `test_summary` already read them.
5. **Generic report writers move to std.** JUnit, CTRF and the console summary
   become std renderers over `std.Result`. hdlsim keeps only the hdlsim-specific
   extras.

## 3. The format

### 3.1 Types (std library, `std/flow.yaml`)

```yaml
types:
- name: Diagnostic          # same shape as TaskMarker, plus DV fields
  with:
    severity:  {type: str}  # info | warning | error | fatal
    msg:       {type: str}
    category:  {type: str}  # uvm | sva | sim | tool | check | ...
    loc:       {type: map}  # {path, line, pos}; path is usually the log
    src_loc:   {type: map}  # optional {path, line}: the source file/line the message reports
    time:      {type: str}  # optional sim time
    hier:      {type: str}  # optional instance path

- name: Metric               # one number worth showing, comparing, trending
  with:
    value:  {type: float}
    unit:   {type: str}      # "ns", "MHz", "cells", "%", "s", "MB" ...
    better: {type: str}      # higher | lower | none -- direction for run-to-run compare
    label:  {type: str}      # optional display name

- name: Check                # a named success criterion: the "why" behind the status
  with:
    name:   {type: str}      # "timing", "uvm_errors", "line_cov_goal", "no_latches"
    status: {type: str}      # pass | fail | error | skip
    metric: {type: str}      # optional: key in metrics this check reads
    op:     {type: str}      # optional: ">=", "<=", "==" ...
    goal:   {type: any}      # optional threshold
    msg:    {type: str}

- name: Result
  uses: DataItem
  with:
    name:       {type: str}   # display name, unique among siblings
    status:     {type: str}   # pass | fail | error | timeout | skip | notrun
    passed:     {type: bool}  # status == "pass"; kept for test_summary/covsight
    msg:        {type: str}   # headline: "UVM_ERROR x2: ch1 mismatch" / "WNS -0.12ns @ clk_sys"
    task:       {type: str}   # fully-qualified producing task
    rundir:     {type: str}
    tool:       {type: map}   # {name, version}: verilator 5.030, yosys 0.45, sby ...
    attrs:      {type: map}   # identity/config: testname, seed, top, part, strategy ...
    metrics:    {type: map}   # name -> Metric (or a bare number)
    checks:     {type: list}  # Check
    counts:     {type: map}   # true totals: diagnostics by severity; for a node with
                              # children, also leaf statuses (pass/fail/error/notrun)
    diagnostics: {type: list} # Diagnostic, capped (first N by severity)
    artifacts:  {type: list}  # std.FileSet with attributes.role (see 3.2)
    children:   {type: list}  # nested Result: cases of a suite, stages of a synth run ...
    start_time: {type: str}
    end_time:   {type: str}
    reused:     {type: bool}  # up-to-date / cache hit: artifacts are from an earlier run

- name: TaskResult            # what dfm synthesizes for a task with no Result (4.2)
  uses: Result
```

The domain types are thin and come in §3.4. Rules:
- **`status` is the verdict, and `checks` explain it.** A node fails if any check
  fails or the work itself broke. Tests use checks like `uvm_errors == 0` and
  `sim_exit == 0`. Synthesis uses `timing: wns_ns >= 0` and `area: cells <= 12000`.
  A coverage goal is `line_cov_pct >= 90`. Renderers show the failing checks
  without knowing the domain. `passed` is derived (`status == "pass"`). `error`
  means no clean verdict (a crash, a tool error, a nonzero exit with a clean log).
  `notrun` means the item was selected but didn't run because something it
  depends on failed.
- **Metrics are the domain payload.** They are typed numbers with units and a
  direction, so a renderer can tabulate, compare and trend any domain's results
  (fmax across runs, sim time across a regression) with no domain code. Cheap
  provenance that is not a quantity goes in `attrs`.
- **The type of a node says its domain, and the tree shape says its structure.**
  There is no `kind` enum to keep up to date. In `results.json` each node carries its
  `type` and its `is-a` lineage (`"types": ["hdlsim.TestResult", "std.TestResult",
  "std.Result"]`). A renderer that doesn't know `hdlsim.TestResult` still knows
  `std.TestResult`, and in the worst case `std.Result`.
- **Failure is data, not task status.** The current hdlsim convention stays: a task
  that reports a failing verdict returns status 0. A non-zero task status means the
  flow itself broke, and those tasks appear as `std.TaskResult` nodes (§4.2).
- **Diagnostics are capped, counts are not.** Each node keeps the first N
  diagnostics (10 today), errors before warnings. `counts` has the true totals. This
  keeps `results.json` small enough for an agent to read whole. Synthesis "critical
  warnings" and formal counterexamples go through the same path.

### 3.2 Artifacts: FileSets with a standard `role`

Artifacts stay `std.FileSet`, so existing consumers that filter on `filetype`
(such as `simCovDb` for `SimCovMerge`) keep working. std standardizes a **role
vocabulary** that renderers understand. `filetype` stays tool-specific. The role
set is open: an unknown role renders as a plain "open file", and `attributes.label`
supplies the display name (for example "Timing (setup)").

| role | meaning | renderer action |
|---|---|---|
| `log` | primary log, which `diagnostics[].loc` points into | open at line |
| `report` | human-readable report: timing, utilization, power, html summary | open |
| `waves` | waveform (fst, vcd, fsdb) or a formal counterexample trace | open in wave viewer |
| `cov` | coverage DB, `attributes.format` = vlt-dat / ucdb / vdb ... | open/merge |
| `netlist` | synthesized netlist (json, v, edif) | open / view schematic |
| `checkpoint` | tool database to reopen in the tool's GUI (dcp, odb ...) | "open in tool" command |
| `image` | built binary: bitstream, firmware elf/hex, sim image | reveal |
| `data` | machine data already folded into `metrics` (`sim_stats.json`) | none |
| `profile` | profiler output | open |
| `other` | anything else worth surfacing | open |

hdlsim already sets `role=log|trace|cov|stats` (`vl_sim_runner.py:416-441`). The
renames are `trace` → `waves` and `stats` → `data`, and renderers accept the old
names for one release. Each artifact
also records `mtime` and `size` at run end, which is how staleness is detected (§5.3).

### 3.3 The on-disk run record

```
rundir/out/<run-id>/
  results.json       # schema "dvflow-results/1": {schema, run, summary, result}
  results/           # link tree over the same data (§5.2), on by default
  summary.md         # human rendering of the same data
rundir/out/latest -> <run-id>
```

The run-id is a timestamp (§2 item 2). `results.json` and `results/` are two views
of one record: one for programs, one for `ls` and editors.

`results.json`:

```json
{
  "schema": "dvflow-results/1",
  "run": {"id": "20261031-142210", "root": "wb-dma-example.tests",
          "argv": ["dfm","run","tests","--build","dbg"], "cwd": "...",
          "start_time": "...", "end_time": "...", "exit_status": 1, "host": "..."},
  "summary": {
    "status": "fail",
    "msg": "1 of 6 failed, 1 not run",
    "counts": {"total": 6, "pass": 4, "fail": 1, "error": 0, "notrun": 1},
    "metrics": {"walltime_s": {"value": 212.4, "unit": "s", "better": "lower"}},
    "failures": [
      {"path": "tests/uvm-tests/two-ch", "status": "fail",
       "msg": "UVM_ERROR x2: ch1 dst mismatch @ 0x40",
       "log": {"path": "/abs/rundir/wb-dma-example.two-ch/sim.log", "line": 1873},
       "waves": "/abs/rundir/wb-dma-example.two-ch/waves.fst"},
      {"path": "tests/soc-tests/soc-dma-copy-two", "status": "notrun",
       "msg": "blocked: wb-dma-example.fw-build failed"}
    ]
  },
  "result": { "name": "tests", "type": "std.TestRunResult",
              "types": ["std.TestRunResult", "std.Result"],
              "status": "fail", "children": [ ... ] }
}
```

`summary` is redundant by design. It is the part an agent or a CI step reads, and
dfm computes it the same way for every domain:
- `status`, `msg` and `metrics` are copied from the root node.
- `counts` tallies the statuses of the **leaf** nodes.
- `failures` lists every non-passing leaf, plus `TaskResult` nodes, each with its
  headline, its failing checks, and the first log location and waveform.

For a single-node run, such as a synthesis run with no stages, `counts.total` is 1
and `failures` holds the root node itself with its failed `timing` check. The
reader needs no special case. `result` is the full tree for renderers. A JSON Schema is generated from the
pydantic models, alongside the flow schema (`dfm util schema --result`), and the
schema test covers it like `test_schema_integrity.py`.

### 3.4 Domain profiles

A profile is a `uses: std.Result` subtype. It fixes the `attrs`, `metrics`,
`checks` and artifact roles its producers fill, so renderers can do better than
the generic view. A profile adds few fields of its own, so a generic renderer loses
little.

**Tests** (std, because `std.TestRunner`/`std.TestSuite` already live there)

```yaml
- name: TestResult          # one case
  uses: Result
  with: {testname: {type: str}, seed: {type: int}}
  # attrs: sim, view, group, build   metrics: walltime_s, simtime, maxrss_mb, cov_*_pct
  # checks: uvm_errors, sim_errors, assertions, sim_exit   roles: log, waves, cov, data
- name: SuiteResult         # children: TestResult | SuiteResult
  uses: Result
  with: {total: {type: int}, failed: {type: int}, errored: {type: int}}
- name: TestRunResult       # root of `dfm run tests`; children: suites + TaskResults
  uses: SuiteResult
```

**Synthesis** (in a synthesis library, for example a yosys/nextpnr or vendor flow
package; none exists in this workspace yet)

```yaml
- name: SynthResult
  uses: std.Result
  # attrs:   top, part/pdk, strategy, constraints
  # metrics: cells, luts, ffs, brams, dsps, area_um2, fmax_mhz, wns_ns, tns_ns, power_mw
  # checks:  timing (wns_ns >= 0), area (<= budget), no_latches, no_inferred_tristates
  # children: stages -- synth, opt, place, route -- each a SynthResult with its own
  #           log, metrics and runtime, so "route blew up" is a node, not a grep
  # roles:   log, report (timing / utilization / power), netlist, checkpoint, image
```

Example node (the failing check makes the run fail even though the tool exited 0):

```json
{"name": "synth", "type": "yosys.SynthResult",
 "types": ["yosys.SynthResult", "std.Result"], "status": "fail",
 "msg": "timing not met: WNS -0.12 ns on clk_sys (target 100 MHz)",
 "attrs": {"top": "soc_top", "part": "ice40-up5k"},
 "metrics": {"fmax_mhz": {"value": 98.8, "unit": "MHz", "better": "higher"},
             "wns_ns":   {"value": -0.12, "unit": "ns", "better": "higher"},
             "luts":     {"value": 4211, "unit": "cells", "better": "lower"}},
 "checks": [{"name": "timing", "status": "fail", "metric": "wns_ns",
             "op": ">=", "goal": 0}],
 "children": [{"name": "synth", "...": "..."}, {"name": "pnr", "...": "..."}],
 "artifacts": [{"type": "std.FileSet", "filetype": "textReport",
                "attributes": {"role": "report", "label": "Timing"},
                "basedir": "...", "files": ["timing.rpt"]}]}
```

**Formal** (libformal, replacing its borrowed `hdlsim.TestResult`)

```yaml
- name: FormalResult
  uses: std.Result
  # attrs: engine (sby/vcf), mode (bmc/prove/cover), top
  # metrics: depth, proven, failed, unknown, covered
  # checks: one per property group; children: one per property when the tool reports them
  # roles: log, waves (counterexample trace), report
```

Because every profile has the same core, a regression that runs synthesis, a test
suite and formal under one root renders as one tree with one verdict.

## 4. Producing the tree

### 4.1 Producers and aggregators

- **Leaf producers** are library check tasks (`SimCheck`, `SimUVMCheck`,
  `SimUVMCase`, eval samples, formal checks, pytest). Each emits a `std.TestResult`
  subtype with diagnostics and artifacts filled in.
- **Aggregators** are `std.TestSuite` and a new generic `std.ResultCollect`. They
  gather the `is_a(std.Result)` items from their inputs into a `SuiteResult` with
  `children`. Counts and metrics roll up with the rules hdlsim's `SuiteResult.stats`
  documents today (`_max`/`_mean`); the rule per metric comes from its `better`
  direction and a std `rollup` hint (sum | max | mean). `std.ResultCollect` is
  domain-neutral: it also groups a synth, a test run and a formal run under one node. The roll-up `SimSuiteReport` does today moves here;
  `SimSuiteReport` becomes `std.TestSuite` plus hdlsim's extra metrics.
- **The root** is `std.TestRunner` (which libproject's `tests`/`smoke` already
  build on). It wraps the suite in a `std.TestRunResult` node. It already has the test
  selection (`std.test_select`), so it can add `notrun` entries for selected tests
  that produced no Result, and name the failed task that blocked each one.

### 4.2 What dfm core adds at the end of the run (`cmd_run`)

1. It takes the root's output and keeps the `is_a(std.Result)` item. If there isn't
   one (a non-test root, or a non-root task run by full name), it **synthesizes**
   a `std.TaskResult`: status from the task status, markers → diagnostics,
   output FileSets → artifacts (with roles guessed from filetype), and `run.log` as
   the `log` artifact.
2. It **attaches unaccounted failures.** Every failed task in the root's subgraph
   whose rundir no Result accounts for is added under the root as a `std.TaskResult`
   child, with its markers and its log. This is the piece that puts a compile error
   or a `todo` gate failure into the results instead of leaving it in the console
   scroll.
3. It **stamps artifacts** with mtime and size, and marks `reused` for nodes from
   tasks that were up to date or cache hits.
4. It writes `out/<run-id>/results.json` and `summary.md`, updates `out/latest`, and
   optionally builds the link tree (§5).
5. It runs the console summary from the same tree. `std.test_summary` reads
   `std.Result` and keeps its duck-typed path as a fallback for one release. The
   run's exit status still comes from `runner.status` and is recorded in `run`.
   Writing results never changes the verdict, matching how the summary hook works
   today (`summary_ctxt.py:114`).

`out/<run-id>` is allocated for every run, not just for publish. Retention is
configurable (`.dfm/config.yaml`, `results.keep: 20`), and the oldest records are
pruned.

## 5. Renderers

### 5.1 Agents and CLI

- `dfm show results [--run ID|latest] [--failures] [--json]` reads `results.json`, so
  nothing else has to parse the rundir. `--json --failures` prints just `summary`.
- `dfm mcp` gets a `get_results` tool with the same output.
- The agent skill (dv-flow-manager) says: after `dfm run`, read
  `rundir/out/latest/results.json` → `.summary`, then open the log at the given line.
  This replaces "search rundir for sim.log".

### 5.2 Link tree (`out/<run-id>/results/`, on by default, `--no-results-tree` to skip)

```
results/
  FAILED/                         # one link per failing/erroring/notrun node
    two-ch -> ../tests/uvm-tests/two-ch
  tests/
    uvm-tests/
      two-ch/
        STATUS                    # "fail: UVM_ERROR x2: ch1 dst mismatch @ 0x40"
        log -> /abs/rundir/wb-dma-example.two-ch/sim.log
        waves.fst -> /abs/rundir/wb-dma-example.two-ch/waves.fst
        rundir -> /abs/rundir/wb-dma-example.two-ch
      smoke/ ...
    soc-tests/ ...
    _tasks/
      fw-build/                   # an unaccounted failure (4.2 step 2)
        STATUS
        log -> /abs/rundir/wb-dma-example.fw-build/run.log
```

The tree is laid out by Result name, not by task-directory name. Today the case
`smoke` lives in `wb-dma-example.smoke-case`, while `wb-dma-example.smoke` is the
suite report; the tree removes that confusion. It is cheap, works with `ls`, `less`
and any editor, and it is what the lab walkthroughs should point to.

### 5.3 Staleness

Task rundirs are reused across runs, so the waves an old record links to may have
been overwritten since. This design does not copy waves or coverage, because they
are too large. Instead:
- Every artifact records `mtime` and `size` (§4.2 step 3). A renderer that sees a
  mismatch shows the artifact as **stale** rather than silently opening the wrong
  run's file. `dfm show results` does the same.
- `results.copy_logs: true` (off by default) copies `role: log` files into
  `out/<run-id>/logs/`, so old records keep their logs for triage. Logs are small,
  and the log is the artifact people go back to.

### 5.4 VSCode extension

- **Discovery:** it watches `**/rundir/out/*/results.json` under each workspace
  folder. Each rundir is a source, each record is a run, and `latest` is expanded
  by default.
- **Results tree view:** workspace → rundir → run → suite → test, with status icons,
  `msg` as the description, and metrics in the tooltip. Nodes of a known profile
  get a richer panel (a test's diagnostics and waves; a synth run's metric table,
  stage timeline and timing report). Any other node gets the generic panel:
  checks, metrics, diagnostics, artifacts.
- **Actions:** open log at `diagnostics[].loc`; open `waves` with a wave-viewer
  extension or an external command; show coverage; reveal the rundir; re-run one
  test (`dfm run <root> --tests <name>`, via the existing `--usage --json` contract).
- **Problems panel:** diagnostics already have the TaskMarker shape, so they map
  directly to VSCode diagnostics. `src_loc`, when present, puts the error on the
  source line rather than the log.
- **Compare runs:** new failures and fixed items between two records, matched by
  result path, and **metric deltas** colored by `better` (fmax down 4% is red, LUTs
  down is green). Across many records this becomes a QoR or runtime trend. All of
  this is generic, because metrics carry their own unit and direction.
- **Live updates (phase 2):** dfm's event stream (`DFM_EVENT_SINK`,
  `task_listener_events.py`) gets a `task.result` event carrying each Result as it
  is produced. The extension shows tests going green and red during the run, then
  reloads `results.json` on `run.end`.

The extension depends only on the JSON Schema. It never reads `exec_data.json` or
guesses rundir layouts, which is the freedom over rendering the format is meant to
give.

## 6. The root-task restriction

**Rule:** a `scope: root` task's output port carries exactly one `std.Result` (an
is-a match) and nothing else. Its `produces:` must say so.

**Why it is the right restriction:** a root task is what a user runs, whether
`tests`, `synth`, `formal` or `lint`. Its output has
no consumer in the graph except the run record, so it should be in the format the
run record uses. It also makes "what does `dfm run X` give me" answerable for every
`X`.

**What it breaks, and the fix:**
- A task that `needs:` a root task stops seeing the root's FileSets. Today the only
  case is libproject's `coverage`, which needs `tests` (`SimCovMerge` consumes the
  `simCovDb` FileSets). Fix: a std helper,
  `std.result.artifacts(inputs, role="cov")`, walks a Result tree and returns its
  artifact FileSets. `SimCovMerge` (and `covsight.Import`, which already reads
  hdlsim `TestResult`/`SuiteResult`) uses it. This is an improvement: each coverage
  DB arrives with its test name, seed and status attached, which covsight needs
  anyway.
- Roots that produce no Result (`build`, codegen, docs, lab1's `std.Null` `tests`).
  These get a synthesized Result (§4.2 step 1), so nothing has to change.

**Rollout:**
1. **Phase A:** `dfm validate` and graph build give a **warning** for a root task
   with no Result in `produces:`. At run time, dfm synthesizes a Result and
   continues. The output port is not yet filtered.
2. **Phase B:** filter the root output port to Result items. This lands together
   with the `SimCovMerge`/covsight change.
3. **Phase C:** setting `results.strict_roots: true` makes the warning an error.
   This becomes the default once the std and lib packages comply.

The check is built on existing machinery: a `requires:` check
(`std.check.Produces{type: std.Result}`, next to `std.check.Needs` in
`std/checks.yaml`) that `std.TestRunner` and the libproject roots declare, plus a
built-in rule for `scope: root` in `ProducesEvaluator`.

## 7. Library changes

**libhdlsim**
- `TestResult uses: std.TestResult` and `SuiteResult uses: std.SuiteResult`. Keep the
  extra fields (`errors`, `warnings`, `fatals`, `sim_errors`, `sim_fatals`,
  `assertion_failures`, `run_status`, `runinfo`) and fill `counts`/`attrs` from them
  as well.
- Map `diagnostics` to the `Diagnostic` shape: `log_line` → `loc.line`, the log
  → `loc.path`, and `file`/`line` → `src_loc`.
- Set `msg` to the first error (the line `SimSuiteReport` already prints per failure).
- Rename artifact roles `trace` → `waves` and `stats` → `data`. Fill `metrics` from
  `stats` with units and directions; `stats` stays as an alias for one release.
- Express the verdict table (`uvm_log_parser.py:20-66`) as `checks`, so a failure
  says *which* rule failed.
- `SimSuiteReport`: hand the roll-up and the JUnit/CTRF writers to std. hdlsim keeps
  `report.json` for one release with a note that it is superseded by `results.json`,
  and declares it in `produces:`.

**libproject**
- `tests`, `smoke`, `coverage`, `profile` and `tests-info` declare their Result
  types. `coverage` emits a Result with `metrics.cov_*_pct`, a `coverage_goal` check, and the merged DB as a
  `cov` artifact. `tests-info` emits a `std.TaskResult` with `tests-info.json` as
  a `report`.
- Fix the gap: the `run` compound in `dv/uvm/utils/flow.yaml:255-284` has no check
  step, so wired into `tests` it yields "no tests ran". Add `SimUVMCheck`.

**libformal**
- Add `FormalResult uses: std.Result` and emit it from `sby_bmc.py` and
  `vcf_analyze.py` instead of `hdlsim.TestResult`. Counterexample traces become
  `waves` artifacts. Formal cases still roll up under `std.TestSuite`, because
  `std.ResultCollect` takes any `std.Result`.

**Synthesis (new library, or wherever the first synth flow lands)**
- `SynthResult` per §3.4. It parses the tool's stats and timing into `metrics`,
  turns goals given as task params (`fmax_mhz`, `max_luts`) into `checks`, and
  makes one child per stage. This is the test of whether the core is really
  domain-neutral, so it should be built early even as a prototype (phase 3b),
  before the root restriction becomes strict.

**dv-flow-mgr std**
- New: the types in §3, `std.ResultCollect`, `std.result` helpers, JUnit/CTRF/summary
  renderers (generic: a node with no test profile becomes one testcase per check,
  so CI dashboards show a timing failure next to the test failures), `dfm show results`, the result writer and link tree, and the
  `std.check.Produces` check.
- `std.EvalSample` `uses: std.TestResult`. This delivers the CTRF output
  `std/evals.yaml` promises but no code implements.

## 8. Phasing

| # | Deliverable | Repo |
|---|---|---|
| 1 | `std.Result` types + JSON Schema; `cmd_run` writes `out/<run-id>/results.json` with synthesis and unaccounted-failure attachment; `dfm show results` | mgr |
| 2 | hdlsim `TestResult`/`SuiteResult` extend std; diagnostics mapping; `msg`; role rename | libhdlsim |
| 3 | `std.ResultCollect`, std JUnit/CTRF/summary renderers; `SimSuiteReport` shrinks; `test_summary` reads `std.Result` | mgr, libhdlsim |
| 3b | Prototype `SynthResult` (yosys) and `FormalResult` (libformal) as checks that the core is domain-neutral | synth lib, libformal |
| 4 | Link tree, `FAILED/`, staleness stamps, retention, `copy_logs` | mgr |
| 5 | `notrun` synthesis in `std.TestRunner`; libproject `produces:` + `run` check fix | mgr, libproject |
| 6 | Root restriction phases A→C; `std.result.artifacts`; `SimCovMerge` + covsight on Result artifacts | mgr, libhdlsim, covsight |
| 7 | VSCode extension tree view + problems; then `task.result` events for live updates; `dfm mcp get_results` | extension, mgr |
| 8 | Docs: labs and wb-dma README point to `rundir/out/latest/results/` and `dfm show results` | this workspace |

Phases 1 and 2 already deliver the agent use case. Phase 4 delivers the symlink
use case. Neither waits on the root restriction.

## 9. Open questions

- **Q1. Strictness:** filter the root output port (Phase B), or only require that a
  Result is *among* the outputs? Filtering is cleaner, and as far as the
  investigation found, it breaks only `coverage needs: tests`.
- **Q2. History:** is mtime/size staleness detection plus optional log copying
  enough, or do you want per-run task rundirs (the `out/<run-id>` layout that
  `docs/RundirLayout.md` describes but the code doesn't implement)? Per-run rundirs
  fix staleness for real, but cost disk space and break up-to-date checks across runs.
- **Q3. Extension home:** `cmds/show/usage.py:88` refers to an existing "vscode
  extension" contract. Should the results view go in that extension (not in this
  workspace), or in a new one?
- **Q4. `passed` type clash:** `hdlsim.TestResult.passed` is a bool, but
  `hdlsim.SuiteResult.passed` is an int count, and `test_summary` tells them apart by
  whether `total` is present. Since `SuiteResult` now extends `Result`, `passed` must
  be a bool on every node, and the pass count moves to `counts.pass`. covsight reads
  `SuiteResult` (`sources.py:73-91`), so either it moves in the same change, or
  hdlsim keeps an `npassed`-style shim for a release. Which do you prefer?
- **Q5. Seeds:** `seed` is a first-class `TestResult` field, but nothing in the
  stack sets seeds (they are read back out of plusargs, `sim_stats.py:506`). Should
  seed/repeat axes in `std.TestRunner` be part of this work?
- **Q6. Where do domain profiles live?** Tests are in std because `std.TestRunner`
  is. Should `SynthResult`/`FormalResult` be std profiles too (so renderers can
  depend on a stable vocabulary for `wns_ns`, `fmax_mhz`, ...), or belong to their
  libraries with only the role and metric-naming conventions in std? I lean to
  library-owned types plus a std **metric-name registry** (`docs/result-metrics.md`)
  that profiles conform to.

## Appendix: incidental findings

- `summary_builtin._load_disk_result` hardcodes `exec_data.json`
  (`summary_builtin.py:140`), but the default legacy layout writes
  `<name>.exec_data.json`. `task_listener_report.py:99` gets this right.
- `docs/RundirLayout.md` (info/, tasks/, out/<run-id>) does not match the layout the
  code writes (per-task dirs directly under `rundir/`).
- The std YAML files reference schema `https://dv-flow.github.io/flow.dv.schema.json`,
  but the generator emits `$id` `dv.flow.schema.json` (`cmd_schema.py:103`).
- `std/evals.yaml` promises CTRF output, but no code implements it.
