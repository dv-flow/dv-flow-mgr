# dv-flow-mgr — Implemented Feature Inventory (source-of-truth)

Scope: `src/dv_flow/mgr/` plus bundled `std/flow.yaml`, `std/filters.yaml`, `share/`.
Every item below was confirmed by reading the code. `file:line` references are relative to `src/dv_flow/mgr/` unless noted.

---

## 1. CLI (`__main__.py` `get_parser`)

### Global options (apply before the subcommand)
- `--log-level {NONE,INFO,DEBUG}` — configure logging level (`__main__.py:107`).
- `-D NAME=VALUE` (repeatable) — parameter override; package (`param=value`), task (`task.param=value`), or `pkg.task.param=value`; lists auto-convert (`__main__.py:110`).
- `-P/--param-file FILE_OR_JSON` — JSON file path or inline JSON string for complex params; `-D` takes precedence (`__main__.py:119`).
- `--package-map FILE` (repeatable) — package-map file (name→flow file) for import-by-name resolution (`__main__.py:125`).
- Subcommand is **required** (`__main__.py:135`).
- Env: `DV_FLOW_PACKAGE_MAP` (colon-style list) consulted by loader (`package_loader.py:76`); `DV_FLOW_PATH` package search path (`ext_rgy.py:168`); `DV_FLOW_CACHE` enables cache providers (`cmd_run.py:244`); `DFM_SERVER_SOCKET` switches dfm into client mode (`__main__.py:739`).

### `run` (`__main__.py:163`, impl `cmds/cmd_run.py`)
- positional `tasks` (zero or more; with none, prints available root tasks) (`:164`, behavior `cmd_run.py:123-155`).
- `-j N` — parallelism, default -1 = all cores (`:165`).
- `--clean` — wipe rundir first (`:168`).
- `--base-rundir PATH` — reuse artifacts from a pre-built rundir; present tasks treated up-to-date (`:171`; wired `cmd_run.py:240` → `runner.base_rundir`).
- `-f/--force` — force all tasks, ignore up-to-date (`:177`; `runner.force_run` `cmd_run.py:254`).
- `-v/--verbose` — show up-to-date tasks too (`:180`).
- `--root DIR` (`:183`); `-c/--config NAME` (`:185`).
- `-u/--ui {log,progress,progressbar,tui}` — console UI; auto: progress if TTY else log (`:187`, `cmd_run.py:53-67`).
- `-D` (`:191`), `-P/--param-file` (`:199`).
- `--runner NAME` — `local`, `lsf`, or omit for auto-detect (daemon if running else local) (`:203`; logic `cmd_run.py:200-221`).
- `--runner-opt KEY=VALUE` (repeatable) (`:207`).
- `--override TARGET=REPLACEMENT` (repeatable) — e.g. `pkg.Task=std.Null` (`:213`; `builder.addOverride` `cmd_run.py:232`).
- `--report DIR` — write diagnostics bundle after run (`:219`; `TaskListenerReport` `cmd_run.py:273-301`).

### `graph` (`__main__.py:137`, impl `cmds/cmd_graph.py`)
- positional `task` (optional) (`:139`); `-f/--format` default `dot` (`:140`); `--root` (`:142`); `-c/--config` (`:144`); `-o/--output` default `-` (`:146`); `-D` (`:149`); `--show-params` (`:155`); `--json` wrap in JSON w/ markers (`:158`).

### `complete` (`__main__.py:228`, impl `cmds/cmd_complete.py`)
- positional `prefix` (optional); `--root`; `-c/--config` — tab-completion candidates for task names (`:228-236`).

### `show` (`__main__.py:238`, impl `cmds/cmd_show.py` + `cmds/show/`)
Common args helper (`--search`, `--regex`, `--tag TagType[:field=value]`, `--json`, `-v/--verbose`, `-D`, `-c/--config`, `--root`) at `__main__.py:246`.
- `show packages` (`:271`).
- `show tasks` (`:277`) + `--package`, `--scope {root,export,local}`, `--produces PATTERN` (`:280-286`).
- `show task NAME` (`:290`) + `--needs [DEPTH]` (dep chain), `--json`, `-v`, `-D`, `-c`, `--root` (`:293-314`).
- `show types` (`:318`) + `--package`, `--tags-only` (derive from std.Tag), `--data-items-only` (derive from std.DataItem) (`:321-328`).
- `show tags` (`:332`) + `--search`, `--json`, `-v`, `-D`, `-c`, `--root` (`:334`).
- `show package NAME` (`:355`) + `--json`, `-v`, `-D`, `-c`, `--root`.
- `show project` (`:377`) + `--imports`, `--configs`, `--json`, `-v`, `-D`, `-c`, `--root`.
- `show skills [NAME]` (`:404`) + `--search`, `--package`, `--full`, `--json`, `-v`, `-D`, `-c`, `--root` — lists DataSet types tagged `AgentSkillTag` (impl `cmds/show/cmd_show_skills.py`).

### `cache` (`__main__.py:435`, impl `cmds/cmd_cache.py`)
- `cache init CACHE_DIR [--shared]` — initialize (optionally group-shared) cache dir (`:440-447`, impl `cmds/cache/cmd_init.py`).

### `validate` (`__main__.py:452`, impl `cmds/cmd_validate.py`)
- positional `flow_file` (optional, auto-detect); `--json`; `-D`; `-c`; `--root` (`:454-470`).

### `context` (`__main__.py:473`, impl `cmds/cmd_context.py`)
- `--json` (default), `--imports`, `--installed`, `-v`, `-D`, `-c`, `--root` — emit project context for LLM agents (`:475-497`).

### `agent` (`__main__.py:499`, impl `cmds/cmd_agent.py`)
- positional `tasks` (skills/personas/tools/references context refs) (`:501`).
- `-a/--assistant {copilot,codex,mock,native}` (`:504`); `-m/--model` (`:507`); `--root` (`:509`); `-c/--config` (`:511`); `-D` (`:513`).
- `--config-file FILE` — dump generated system prompt instead of launching (`:519`); `--json` — dump context JSON (`:521`); `--clean` (`:524`); `--ui {log,progress,progressbar,tui}` (`:527`).
- `--approval-mode {never,auto,write}` — tool-approval gating for native agent (`:530`).
- `--trace` — enable agent tracing to `~/.dfm/traces/` (`:534`).

### `mcp` (`__main__.py:539`, impl `_CmdMcp` `__main__.py:43`)
- positional `tasks`; `--root`; `-c/--config` — start DFM as an MCP stdio server; requires `dv-flow-mgr[agent]` (`run_mcp_server`, `cmds/agent/dfm_mcp_server.py`).

### `daemon` (`__main__.py:550`, impl `cmds/cmd_daemon.py`)
- `daemon start` + `--root`, `--runner`, `--pool-size N`, `--monitor`, `--foreground` (`:554-568`).
- `daemon stop` + `--root` (`:570`).
- `daemon status` + `--root`, `--json` (`:575`).

### `worker` (`__main__.py:585`, impl `_CmdWorker` `__main__.py:77`)
- `--connect host:port` (required), `--worker-id`, `--resource-class`, `--lsf-job-id` — internal worker process spawned by daemon/pool (`:587-599`).

### `util` (`__main__.py:601`, impl `cmds/cmd_util.py`)
- `util CMD [args...]` — internal utility; currently only `workspace` (dumps package JSON / markers) (`cmd_util.py:9-40`).

### Separate console entry point
- `dfm-out` — shell-task output helper, its own argparse CLI (`out.py`); see §4.
- `dv_flow.mgr.util.__main__` — a separate util CLI with `schema` subcommand (`util/cmds/cmd_schema.py`).

> Note: there is **no `dfm init` command** in `get_parser`; the only `init` is `cache init`.

---

## 2. Flow-spec language features

### Package (`package_def.py:47 PackageDef`)
- `name`, `desc` (`:50,:52`); `uses` base-package inheritance (`:79`); `with:` package params (`:82`).
- `imports` — strings or import specs (`:64`); `package-map` one/many name→file maps (`:67`); `overrides` map target→replacement-name|inline-def (`:70`); `fragments` file list (`:73`); `types`, `tasks`, `filters`, `configs`, `tags` (`:55-90`).

### Fragment (`fragment_def.py:33 FragmentDef`)
- Optional `name` (prefixes tasks `<pkg>.<name>.<task>`) (`:36`); `tasks`, `filters`, `imports`, nested `fragments`, `types`, `configs` (`:39-57`).

### Imports (`package_import_spec.py`)
- By name: `name` field (`:50`); by path/identifier: `from:` (alias of `path`) (`:53`); `as:` alias (`:57`); `config:` to apply a configuration (`:61`); `with:` param overrides (`:65`).
- Import-by-name resolved via package-maps (`package_provider_yaml.py:363`, `package_loader.py:192 add_package_map`) and `DV_FLOW_PATH` search (`ext_rgy.py:120 _findOnPath`).
- "Lazy" package loading: provider/loader resolve packages on demand (`package_provider.py`, `package_loader.py`, `package_map_provider.py`).

### Config / Configurations (`config_def.py:40 ConfigDef`)
- `name`, `with:` params, `uses:` base config (`:41-49`); `overrides` (OverrideDef list) (`:50`); `extensions` (ExtendDef) (`:53`); per-config `imports`, `fragments`, `tasks`, `types` (`:56-67`).
- `OverrideDef` (`config_def.py:8`): target via `task:` / `package:` / legacy `override:`, replacement via `with:` (str name or inline dict).

### Task definition (`task_def.py:200 TaskDef`)
- Name + inline scope markers: `name` / `root` / `export` / `local` / `override` (mutually exclusive; consolidated into `name`+`scope`) (`:203-222`, validator `:305`).
- `scope` explicit (`root`/`export`/`local` or list) (`:227`).
- `uses` (base type) (`:223`); `needs` (deps) (`:264`); `feeds` (inverse deps) (`:267`); `with:`→`params` (`:270`).
- Body via `body`/`tasks` alias (compound) (`:231`); `iff` enable condition (`:235`).
- Implementation: `run` (shell body) (`:242`), `shell` (default `bash`) (`:245`), `pytask` (deprecated python impl) (`:239`).
- `template: true` — defer `run`-expression to graph-build time (`:248`); cannot combine with `override` (`:356`); direct invocation rejected (`task_graph_builder.py:474`).
- `strategy` (`:251`) / `control` (`:253`) — mutually exclusive (validator `:351`).
- `desc`, `doc` (`:256-263`).
- `rundir: {unique|inherit}` (`RundirE` `:42`, field `:274`).
- `passthrough: {none|all|unused}` or list (`PassthroughE` `:50`, field `:277`).
- `consumes: {none|all}` or list of match patterns (`ConsumesE` `:46`, field `:280`).
- `produces` — list of match dicts (`:283`).
- `uptodate: false|<python method>|null` (`:286`).
- `cache: true|false|CacheDef` (`:289`; bool auto-normalized `:313`).
- `tags` — type refs w/ optional overrides (`:292`).
- `max_failures` (`:295`) and `on_error` python hook (`module:function`) for compound tasks (`:299`).

### Strategy (`task_def.py:62 StrategyDef`)
- `matrix: {key: [values]}` — one task per combination (`:69`; expansion `task_graph_builder.py:826-950`, exposes `${{ matrix.key }}` and `this.<key>`).
- `generate: {shell, run}` — run shell cmd that emits YAML task defs to stdout (`GenerateSpec :55`; `ExecGenCallable` `task_graph_builder.py:820`, `exec_gen_callable.py`).
- `chain: bool` — run body tasks sequentially, each consuming previous output (`:63`).
- `body:` list of sub-TaskDefs (`:72`).

### Control flow (`task_def.py:116 ControlDef`) — runtime control constructs
- `type: if|match|while|do-while|repeat` with field validation (`:143-166`).
- `if` needs `cond` (+ `else`) (node `task_node_if.py`); `match` needs `cases` (ControlCaseDef `when`/`default`/`body`) (`task_node_match.py`); `while` needs `cond`+`max_iter` (`task_node_while.py`); `do-while` needs `until`+`max_iter` (`task_node_do_while.py`); `repeat` needs `count` (`task_node_repeat.py`).
- Loop `state` (init/feedback/type) for carrying state across iterations (`ControlStateDef :104`).

### Extend (`extend_def.py:6 ExtendDef`)
- Extend an existing task by name: add `with:` param modifications, `uses:`, and extra `needs` (`:8-19`).

### Type definition (`type_def.py:27 TypeDef`)
- `name`, `uses` (base type), `doc`, `with:` params, `tags` (`:28-42`).

### Param definition (`param_def.py:47 ParamDef`)
- `type` (`str`/`int`/`bool`/`list`/`map` or ComplexType list/map) (`:54`, ComplexType `:37`); `value` default (`:57`).
- List/path mutators: `append`/`prepend` (`:60,:63`), `path-append`/`path-prepend` (OS-sep) (`:66,:70`); resolution logic `resolve_value` (`:76`).
- `doc`/`desc` (`:48,:51`). `VisibilityE {local,export}` enum (`:43`).

---

## 3. Task implementation mechanisms

- Shell-to-callable registry: `shell` (alias bash), `bash`, `csh`, `tcsh` → `ShellCallable`; `pytask` → `ExecCallable` (`ext_rgy.py:151-155`). Plugins can add shells via `dfm_shells`/`dvfm_shells` entry points (`ext_rgy.py:206`).
- Shell tasks: `run` body + `shell` selector; multi-line bodies written to a `*_cmd.sh` script, single-line run via `shell -c`; `${{ this.p }}`, `${{ p }}`, `${{ rundir }}` expanded in the body (`shell_callable.py:37-107`).
- Pytask (inline): `shell: pytask` + `run: module.func` — resolves to a python callable (`ExecCallable`); used throughout std (e.g. `std/flow.yaml:35`). `pytask:` field on TaskDef is the deprecated form (`task_def.py:239`).
- Class-based PyTask API: `PyTask` descriptor base (`pytask.py:10`) with `@pytask(pkg)` registration decorator (`:52`); `params` property exposes typed Params.
- PyPkg factory: `PyPkg` + `@pypkg` (`pypkg.py:9,:43`) — **partial/experimental** (registerTask has debug `print`s and assumes `Params.a`).
- Plugin discovery via entry-point group `dv_flow.mgr`: packages (`dvfm_packages`/`dfm_packages`), runners (`dfm_runners`), shells (`ext_rgy.py:177-217`).
- Hash providers (for incremental hashing): SV provider (priority 10) + default (priority 0), pluggable (`ext_rgy.py:71-94,:163`; `hash_provider_sv.py`, `hash_provider_default.py`).

---

## 4. Script I/O contract (`data_io.py`, `out.py`)

GitHub-Actions-style: **env vars for input, append-only files for output** (filenames are stable contract; `data_io.py:43-52`).

### Input env vars set by the runner (`data_io.py:127 stage_inputs`)
- `DFM_RUNDIR`, `DFM_SRCDIR`, `DFM_TASK_NAME` (`:184-186`).
- `DFM_PARAMS` → `dfm.params.json` (full params) (`:187`); `DFM_PARAM_<NAME>` per-declared-param scalar (lists/maps as compact JSON, bools `true`/`false`) (`:153-155`, `_scalar_to_env :76`).
- `DFM_INPUTS` → `dfm.inputs.json` (consumed items array) (`:188`).
- `DFM_MEMENTO` → `dfm.memento.json` (prior memento, only if present) (`:172`).
- Legacy aliases still set by shell tasks: `TASK_SRCDIR`, `TASK_RUNDIR` (`shell_callable.py:44-45`).

### Output env vars / files harvested by the runner (`data_io.py:265 harvest_outputs`)
- `DFM_OUTPUT` → `dfm.output.jsonl` — typed data items (JSONL; `std.FileSet` `basedir:"."`→rundir) (`:189,:303`).
- `DFM_ENV` → `dfm.env` — `KEY=VALUE` + heredoc form; folded into a `std.Env` item (`:190,:198,:334`).
- `DFM_PATH` → `dfm.path` — one dir/line, folded into `std.Env.prepend_path[PATH]` (`:191,:334`).
- `DFM_MARKERS` → `dfm.markers.jsonl` — `{severity,msg,loc?}` JSONL (`:192,:356`).
- `DFM_MEMENTO_OUT` → `dfm.memento.out.json` — opaque script-owned blob (`:193,:373`).
- Unknown emitted `type` falls back to `_DuckItem` + warning marker (`:285-301`).

### `dfm-out` helper (`out.py`)
- Subcommands: `fileset [--filetype --basedir --incdir] FILES...`, `item --type T [k=v|k:=json]`, `env KEY=VALUE...`, `path DIRS...`, and marker verbs `error`/`warning`/`info MSG [--file --line --pos]` (`out.py:132-161`).
- `k:=v` parses value as JSON-typed; `k=v` is string (`_parse_kv :57`).
- Writes by appending to the relevant `DFM_*` file; errors clearly if run outside a task (`_append_line :42`).
- Resolved on PATH inside shell tasks via an auto-generated shim that re-invokes `python -m dv_flow.mgr.out` (works from source checkout) (`shell_callable.py:124 _ensure_dfm_out_shim`).

---

## 5. Standard library (`std/flow.yaml`, `std/filters.yaml`, `std/*.py`)

### Tasks (`std/flow.yaml`)
- `std.Message` — print `msg` (`:34`; impl `std/message.py:24`).
- `std.FileSet` — glob/list → fileset; `base,type,incdirs,defines,attributes,include,exclude`; passthrough all / consumes none; has up-to-date check (`:41`; impl `std/fileset.py:38`, `FileSetUpToDate`).
- `std.CreateFile` — write literal content → fileset; `type,filename,content,incdir`; content-hash memento (`:74`; impl `std/create_file.py:37`).
- `std.SetEnv` — `setenv,append_path,prepend_path` maps → `std.Env`; glob-expands values vs srcdir; memento (`:95`; impl `std/setenv.py:23`).
- `std.SetFileType` — re-stamp `filetype` on input filesets (`:108`; impl `std/set_file_type.py`).
- `std.IncDirs` — derive include dirs from input filesets (`:118`; impl `std/incdirs.py`).
- `std.Agent` — run an AI assistant, parse JSON result; params `system_prompt,user_prompt,result_file,assistant,model,sandbox_mode,approval_mode,max_retries,assistant_config` (`:125`; impl `std/agent.py:173`).
- `std.Null` — no-op passthrough (`:202`; impl `std/task_null.py`).
- `std.RunTasks` — dynamically schedule tasks from `std.TaskRunSpec` inputs; fail-fast; optional `timeout` (`:209`; impl `std/run_tasks.py:34`).
- (`std/data_item.py DataItem` exists in code but is **not registered** in flow.yaml.)

### Types (`std/flow.yaml`)
- `std.Tag` base (`category,value`) (`:230`).
- Agent tag types: `AgentSkillTag` (`:241`), `AgentToolTag` (`:248`), `AgentPersonaTag` (`:253`), `AgentReferenceTag` (`:258`).
- `std.ResourceTag` — compute requirements: `cores,memory,queue,walltime,resource_class` (used by cluster runners, ignored by local) (`:263`).
- `std.DataItem` base (`:291`); `std.FileSet` (filetype/basedir/files/incdirs/defines/attributes) (`:296`); `std.Env` (vals/append_path/prepend_path) (`:321`).
- Agent resources: `AgentResource` base (files/content/urls) (`:351`); `AgentSkill` (tags AgentSkillTag) (`:370`); `AgentPersona` (`persona`) (`:381`); `AgentTool` (command/args/url) (`:390`); `AgentReference` (`:403`).
- `std.TaskRunSpec` — `task_type,task_name,params,needs` for dynamic execution (`:409`).

### Filters (`std/filters.yaml`, fragment of std)
- `by_filetype`, `by_type`, `pluck`, `first_of_type`, `basenames`, `extensions`, `paths`, `count_by_type` — all jq-style `expr` filters using positional `$arg0…` (`:30-81`).

### Bundled share assets
- JSON schema `share/dv.flow.schema.json`; agent prompts `share/prompts/{copilot_system,general_agent}.md`.
- Bundled agent skill `share/skills/dv-flow-manager/SKILL.md` + references + golden example; discovered via `agent.skills` entry point (`skills.py:14 get_skill_dirs`).

---

## 6. Execution / runtime

- Runner backends registry: `local` (`LocalBackend`), `lsf` (`LsfBackend`) built-in; `slurm` exists but is a **stub** (`ext_rgy.py:158-161`, `slurm_backend.py`).
- Local backend: in-process execution (`runner_backend_local.py`).
- LSF backend: embedded `WorkerPoolHost`, launches workers via `bsub`, dispatches via PoolManager, no daemon required; `is_remote=True`; cancellation supported (`lsf_backend.py:38-149`).
- SLURM backend: every method raises `NotImplementedError` — placeholder only (`slurm_backend.py:35-45`).
- Runner config layering (install→site→project→env/CLI): `RunnerConfig` with `PoolConfig` (min/max workers, idle_timeout), `LsfConfig` (bsub_cmd/queue/project/resource_select/bsub_extra), `ResourceClassDef`, `ResourceDefaults` (`runner_config.py:33-77`).
- Daemon (worker-pool manager): start/stop/status, background or foreground, optional monitor TUI; writes `.dfm/daemon.json`; JSON-RPC over socket (`daemon.py`, `cmds/cmd_daemon.py`). `dfm run` auto-delegates to a running daemon (`cmd_run.py:200-208`, `daemon_client.py DaemonClientBackend.discover`).
- Worker process: connects to daemon (`worker.py run_worker`, `worker_protocol.py`).
- Parallelism via a jobserver token mechanism (`-j`); `ctxt.exec`/`exec_parallel` acquire/release tokens (`task_run_ctxt.py:73-223`, `jobserver.py`).
- Incremental / up-to-date: per-task mementos persisted to `rundir/cache/mementos.json` (`task_runner.py:220-227`); `uptodate` callable hooks; `-f/--force` overrides (`task_runner.py:99`); `changed` flag drives downstream.
- `--base-rundir` artifact reuse: tasks already present in a pre-built rundir are treated up-to-date (`task_runner.py base_rundir`; CLI `cmd_run.py:240`).
- Report bundle: `--report DIR` writes per-task logs/markers/status read from on-disk `exec_data.json`, backend-independent (`cmd_run.py:273-301`, `task_listener_report.py`).
- Caching: provider-based artifact cache enabled via `DV_FLOW_CACHE`; `dfm cache init` creates/share a cache dir; per-task `cache:` config with compression + extra hash exprs (`cmd_run.py:243-248`, `cache_provider*.py`, `cache_config.py`, `task_def.py:76 CacheDef`).
- Resource tags: `std.ResourceTag` declares cores/memory/queue/walltime/resource_class for cluster runners; ignored by local (`std/flow.yaml:263`).
- Dynamic sub-graph scheduling at runtime: `ctxt.run_subgraph(...)` + `runner.schedule_subgraph` (used by `std.RunTasks`) (`task_run_ctxt.py:254`, `dynamic_scheduler.py`).
- Console listeners / UIs: `log`, `progress`, `progressbar`, `tui`, plus JSON trace (`task_listener_*.py`).
- Naming schemes for rundir/log/script/prompt filenames: leaf, legacy, default (`naming_scheme*.py`).

---

## 7. Agent / LLM features

- `dfm agent` — loads project, resolves task refs into agent context (skills/personas/tools/references), builds a system prompt, then launches an assistant (`cmds/cmd_agent.py`).
  - Subprocess assistants: `copilot`, `codex`, `mock` (`AssistantLauncher`, `std/ai_assistant.py`, priority `["copilot","codex"]`).
  - Native assistant: `DfmAgentCore` using the openai-`agents` SDK with `LitellmModel` (any LiteLLM provider via model string/api_key/api_base) + a TUI (`cmds/agent/agent_core.py:109-143`, `cmds/agent/tui.py`); config from YAML w/ `${{ env.X }}` expansion (`cmds/agent/config.py`).
  - Approval modes `never|auto|write`; tracing to `~/.dfm/traces/` (`cmd_agent.py`, `agent_core.py:177`).
  - Native-agent tools: DFM tools + coding tools + MCP servers (`agent_core.py:113-115`, `dfm_tools.py`, `coding_tools.py`, `mcp_setup.py`).
- Server mode / `DFM_SERVER_SOCKET`: when set, `dfm` runs as a JSON-RPC **client** forwarding `run`/`show`/`context`/`validate`/`ping` to the parent session's Unix-socket server (`__main__.py:610-734`, `dfm_server.py DfmCommandServer`/`DfmClient`, socket chmod 0600 `dfm_server.py:134`).
- `dfm context` — comprehensive project context JSON for agents (`cmds/cmd_context.py`).
- `dfm show skills [--json --full]` — lists/queries `AgentSkillTag` DataSets, incl. installed; renders skill_doc (`cmds/show/cmd_show_skills.py`).
- `dfm mcp` — MCP stdio server exposing tools: `dfm_show_tasks`, `dfm_show_task`, `dfm_show_packages`, `dfm_show_types`, `dfm_show_skills`, `dfm_context`, `dfm_validate`, and (when builder/runner present) `dfm_run_tasks` (`cmds/agent/dfm_mcp_server.py:73-163`).
- `std.Agent` task — embeds an assistant in the flow graph (native or subprocess), strict JSON result-file contract, retry logic, prompt/result-hash memento (`std/agent.py`).
- Agent skills shipped as an installable skill bundle, discovered via `agent.skills` entry point (`skills.py`).

> Not found in source: any `AGENTS.md` auto-discovery logic (no references in `src/`). Context is built from task references and `pkg`/`loader`, not from an `AGENTS.md` file.

---

## 8. Expressions, filters, visibility, error handling

### `${{ }}` expressions (`expr_eval.py`, `expr_parser.py`)
- Full expression evaluator: hierarchical IDs, indexing/slicing (`obj[i]`, `obj[a:b]`), iterator `obj[]`, `$var`, arithmetic, comparisons, `and`/`or`/`not`, pipe `|` (`expr_eval.py:184-360`).
- Default-value syntax `name:-fallback` (`expr_eval.py:106,:160`).
- Builtins: `shell`, `length`, `keys`, `values`, `sort`, `unique`, `reverse`, `map`, `select`, `first`, `last`, `flatten`, `type`, `split`, `group_by` (`expr_eval.py:44-59`).
- `shell(...)` builtin runs a subprocess and substitutes stdout; nested `${{ }}` expanded recursively (`expr_eval.py:362-404`).
- Name resolution via `VarResolver`/`NameResolutionContext`; package/env/param scopes (`name_resolution.py`).

### Filters (`filter_def.py`, `filter_registry.py`, `eval_jq.py`)
- Package-level reusable transforms invoked as `${{ inputs | name(args) }}` (`filter_def.py`).
- Implementation either `expr:` (jq-style) or `run:` (shell/python via `shell:`) — mutually exclusive (validator `filter_def.py:160`).
- Visibility markers (`name`/`root`/`export`/`local` or explicit `scope`); `is_visible_to` enforces package/root/export/local/explicit-list rules (`filter_def.py:199-232`).
- Registry resolves filters by current package; jq filters run in a child eval context with `input` + `$arg0…` params (`expr_eval.py:406-460`, `filter_registry.py`).

### Task / filter visibility (scopes)
- `root` (executable / root-package only), `export` (visible to downstream packages), `local` (fragment-only), default (within-package + root); inline markers consolidated to `scope` (`task_def.py:227,:337`, `filter_def.py`).
- Only `scope: root` tasks are listed/runnable as top-level targets (`cmd_run.py:137-145`).
- `show tasks --scope {root,export,local}` filters by visibility (`__main__.py:282`).

### Error handling
- `max_failures` on compound tasks: -1/0 = run all independent subtasks; 1 = stop on first; N>1 = stop after N (`task_def.py:295`, also `run_subgraph` `task_run_ctxt.py:259`).
- `on_error` python hook invoked as the compound's run hook when subtasks complete (`task_def.py:299`).
- Markers with severities (`error`/`warning`/`info`); task failure surfaced via non-zero `status` and error markers; `TaskDataResult` carries status/output/markers/memento/changed (`task_data.py`, `task_run_ctxt.py:236-252`).
- Loaders accumulate markers; commands abort when any `SeverityE.Error` present (`cmd_run.py:99`).

---

## Notably stubbed / partial / internal-only

- **SLURM backend** — fully stubbed; `start`/`execute_task` raise `NotImplementedError` (`slurm_backend.py:35-45`).
- **`PyPkg` class-based package factory** — experimental; `registerTask` contains debug `print`s and hard-codes `T.Params.a` (`pypkg.py:26-39`).
- **`std/data_item.py DataItem`** — implemented (with a debug `print`) but **not registered** in `std/flow.yaml`; reachable only by direct callable reference.
- **`pytask:` TaskDef field / `cond_def.py CondDef`** — marked deprecated / appears legacy (`task_def.py:239`; `cond_def.py` is commented-design scaffolding, not wired into the control-flow path which uses `ControlDef`).
- **jq filters** — `_eval_jq_filter` notes "TODO: Implement native jq operators (Phase 3)"; currently evaluated via the in-house expr engine, and filters use positional `$arg0…` only (no keyword args yet) (`expr_eval.py:430`, `std/filters.yaml:22`).
- **`dfm worker` / `util`** — internal commands (worker spawned by daemon/pool; `util` only implements `workspace`).
- **Server client mode** — the `DFM_SERVER_SOCKET` client path hand-parses a limited arg subset (`run/show/context/validate/ping`), not the full argparse surface (`__main__.py:610-734`).
- **`std.Agent` copilot path** — checks a hard-coded `copilot_output.log` for emptiness heuristics (`std/agent.py:408`).
- No **`dfm init`** command exists despite being commonly referenced; project bootstrap is manual.
