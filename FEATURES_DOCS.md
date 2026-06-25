# DV Flow Manager — Documentation Feature Inventory

Catalog of every feature/capability/command/syntax that the `docs/*.rst` files
**describe or claim**. Organized by the 8 audit categories. Each bullet notes the
**page** it appears on and the specific claim. Forward-looking / "not yet
implemented" / placeholder claims are flagged with **[FORWARD-LOOKING]**.

Pages scanned (all `.rst` under `docs/`, excluding `_build/`):
index, intro, install, quickstart; guide/{index, concepts, packages, tasks,
dataflow, parameters, expressions, filters, visibility, error_handling, stdlib,
running, incremental, runners, developing_tasks, script_io, python_tasks,
advanced}; ai/{index, overview, using_with_agents, agent_resources,
native_agent}; reference/{index, cli, flow_spec, python_api, types_api,
runner_backend_api, runner_config, resource_tags}.

---

## 1. CLI — commands, subcommands, flags, env vars

### Top-level commands (reference/cli "Commands Overview", ai/using_with_agents `dfm --help`)
- **`dfm run`** — execute tasks in a flow. (cli, running, quickstart, intro)
- **`dfm show`** — display/search packages, tasks, types, tags. (cli, dataflow)
- **`dfm agent`** — launch AI assistant with DV Flow context. (cli, ai/*)
- **`dfm context`** — output project context for LLM agents. (cli, ai/using_with_agents)
- **`dfm graph`** — generate visual task dependency graphs. (cli, advanced, tasks)
- **`dfm validate`** — check flow definition for errors / dataflow compatibility. (cli, dataflow)
- **`dfm util`** — "Internal utility commands". (cli, listed in Commands Overview only)
- **`dfm daemon start|stop|status`** + `dfm daemon --monitor` — daemon lifecycle/monitoring. (runners)
- **`dfm ping`** — health check (server mode). (ai/using_with_agents)
- The CLI reference page auto-generates the full parser via `.. argparse:: dv_flow.mgr.__main__: get_parser`. (cli)

### Global / common options
- **`-D NAME=VALUE`** — parameter override; repeatable. Forms: package-level (`-D timeout=300`), leaf (`-D top=counter`), task-qualified (`-D build.top=counter`), fully-qualified (`-D myproject.build.top=counter`). Type coercion to list/bool/int/str. (cli, parameters, ai/using_with_agents)
- **`-P FILE` / `-P '<json>'`** — JSON parameter file or inline JSON string; `-D` takes precedence over `-P`. JSON shape `{package:{...}, tasks:{<task>:{...}}}`. (ai/using_with_agents)
- **`--package-map FILE`** — resolve imports by name via package-map file; repeatable; earlier maps win. (cli, packages)
- **`-c, --config NAME`** — select a package configuration. (cli, packages, running)
- **`--root PATH`** — root directory for the flow (run + context). (cli)
- **`--log-level {NONE,INFO,DEBUG}`** — debug level (shown in `dfm --help`). (ai/using_with_agents)

### `dfm run` options
- **`-j N`** — parallelism (default all cores; `-j 1` sequential). (cli, running, advanced)
- **`--clean`** — remove rundir before build. (cli, running)
- **`-f, --force`** — force all tasks, ignore up-to-date, preserves rundir. (cli, running, incremental)
- **`-v, --verbose`** — show up-to-date tasks too. (cli, running, incremental)
- **`-u, --ui {log,progress,tui}`** — console UI style. (cli, running)
- **`--override TARGET=REPLACEMENT`** — replace a task in graph; repeatable; e.g. `--override sim_pkg.Compile=std.Null`. (cli, tasks, stdlib)
- **`--runner BACKEND`** — runner backend (`local`, `lsf`…); auto-detects daemon. (cli, runners, running)
- **`--runner-opt key=value`** — runner option; repeatable; keys `queue`, `project`, `bsub_cmd`. (runners)
- **`--base-rundir PATH`** — reuse compiled artifacts from a prior build's rundir; read-only/trusted; exports `DFM_BASE_RUNDIR`. (cli, incremental)
- **`--report DIR`** — write self-contained diagnostics bundle after run. (cli, running)
- **`--timeout N`** — mentioned in server-mode examples (`dfm run task1 --timeout 300`). (ai/using_with_agents)

### `dfm show` subcommands + options
- Subcommands: **packages, tasks, task `<name>`, types, tags, package `<name>`, project, skills**. (cli; skills documented in ai/using_with_agents)
- Common options: **`--search KEYWORD`**, **`--regex PATTERN`**, **`--tag TAG`** (`TagType` or `TagType:field=value`), **`--json`**, **`-v, --verbose`**. (cli)
- `show tasks`: **`--package PKG`**, **`--scope {root,export,local}`**, **`--produces PATTERN`** (comma-sep key=value, AND/subset). (cli, dataflow)
- `show task <name>`: **`--needs [DEPTH]`** (DEPTH optional, -1 unlimited). (cli)
- `show types`: **`--tags-only`**, **`--data-items-only`**, **`--search`**. (cli)
- `show tags`: `--search`, `--json`. (cli)
- `show package <name>`: `--json`, `-v`. (cli)
- `show project`: **`--imports`**, **`--configs`**, `--json`, `-v`. (cli)
- `show skills`: `--json`, **`--package PKG`**, **`<name> --full`**, **`--search`**. (ai/using_with_agents)
- Legacy mode: bare **`dfm show`** (lists project tasks); **`dfm show <task> -a`** (dependency tree). (cli)

### `dfm validate`
- **`dfm validate [--json]`**; also `dfm validate flow.yaml` shown in agent workflows. (cli, dataflow, ai/*)

### `dfm agent` options
- **`-a, --assistant {copilot,codex,mock}`** (cli) / also `native` (ai/native_agent, ai/agent_resources). Auto-detect order copilot→codex.
- **`-m, --model MODEL`** (cli, ai/*).
- **`--clean`**, **`--ui {log,progress,tui}`** (cli; ai lists also `progressbar`), **`--json`**, **`--config-file FILE`**. (cli, ai/*)
- **`-c, --config`**, **`-D NAME=VALUE`**. (ai/using_with_agents)
- **`--approval-mode {never,auto,write}`**, **`--trace`**. (native_agent)

### `dfm graph` options
- **`-f, --format {dot}`** (GraphViz DOT, default). **`-o, --output FILE`** (`-` = stdout). (cli, advanced)

### `dfm daemon` options
- **`--runner <name>`**, **`--pool-size <n>`**, **`--monitor`**; `status --json`. (runners)

### Environment variables (CLI/runtime)
- **`DV_FLOW_PACKAGE_MAP`** — colon-separated package-map files. (cli, packages)
- **`DV_FLOW_PATH`** — package registry search path. (packages)
- **`DFM_BASE_RUNDIR`** — exported when `--base-rundir` set. (cli, incremental)
- **`DFM_RUNNER`** — override runner type. (runners, runner_config)
- **`DFM_INSTALL_CONFIG`** — install config path override. (runners, runner_config)
- **`DFM_SERVER_SOCKET`** — set by parent `dfm run`; triggers client/server mode. (ai/using_with_agents)
- **`DFM_MODEL`**, **`DFM_PROVIDER`** — native agent model selection. (native_agent)
- Provider keys: `GITHUB_TOKEN`, `OPENAI_API_KEY`, `OPENAI_API_BASE`, `ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, `GEMINI_API_KEY`, `OLLAMA_HOST`, `OLLAMA_API_BASE`. (native_agent)

---

## 2. Flow-spec language features

### Package / fragment / file root
- **`package:`** with `name`, `tasks`, `types`, `with`, `configs`, `imports`, `fragments`, `filters`, `overrides`, `package-map`, `desc`. (concepts, packages, flow_spec)
- **`fragment:`** root keyword; allowed fields: tasks, types, configs, imports, filters, fragments, name; **NOT allowed**: `with`, `desc` (root-only). Schema `extra="forbid"`. (packages, flow_spec)
- **Nested fragments** — fragments referencing fragments; paths relative to containing file. (packages)
- Optional fragment `name:` prefixes task names `<package>.<name>.<task>`. (packages)

### Imports / package-map
- **Import by path** (file or directory). (packages)
- **Import with explicit location** — `name:` + `from:` (pins file; package.name must match). (packages)
- **Import with alias** — `as:`. (packages)
- **Import by name** — `name:` alone, resolved via package map / registry / `DV_FLOW_PATH`. (packages)
- Resolution order: relative-to-file → project-root → package maps → registry/`DV_FLOW_PATH`. (packages)
- **`package-map:`** key (single or list; earlier wins). Map schema: `package-map: {version: 1, packages: [{name, path}]}`. (packages)
- **Lazy loading** of name-imports (deferred parse); path imports always eager; `dfm run`/`graph` flatten all. (packages)
- Note: maps "typically produced by a dependency manager (e.g. ivpm)". (packages)

### Configs
- **`configs:`** with `name`, `with`, `uses` (base config), `overrides`, `extensions`, `tasks`, `types`, `imports`, `fragments`. (packages)
- Selected via `-c/--config`. Merge order documented. (packages)

### Task fields
- **`name:`** / inline scope markers **`root:` / `export:` / `local:` / `override:`** (mutually exclusive, one per task). (visibility)
- **`uses:`** (base task) vs **`type:`** (equivalent but ambiguous; `uses` canonical). (tasks, quickstart)
- **`needs:`** (direct deps) and **`feeds:`** (inverse). (concepts, tasks, parameters)
- **`with:`** — parameter declarations/overrides; `append:` / `prepend:` for lists; formula `prepend + (value or base_value) + append`. (parameters)
- **`run:`** — shell/python body. **`shell:`** — `bash`(default)/`sh`/`shell`/`csh`/`tcsh`/`python`/`pytask`. (developing_tasks, stdlib)
- **`body:`** — compound task subtasks. (tasks, parameters)
- **`strategy.matrix`** — cartesian expansion; compound-only; `matrix.<var>`. (expressions, developing_tasks)
- **`strategy.generate`** — programmatic subgraph generator (`run:` points at Python). (developing_tasks, advanced, python_api)
- **`template: true`** — defer `run` expansion to graph-build time; cannot be a top-level entry; mutually exclusive with `override:`. (developing_tasks)
- **`override:`** — replace another task package-wide. (tasks, advanced, parameters)
- **`extensions:` / `extend`** (ExtendDef) — modify existing tasks (add params/needs/change base); inherit via `uses`. (packages, flow_spec)
- **`consumes:`** — `all`/`none`/pattern list. (tasks, dataflow)
- **`passthrough:`** — `all`/`none`/`unused`(default)/pattern list. (tasks, dataflow)
- **`produces:`** — list of pattern dicts; inherited+extended via `uses`; `${{ params.X }}` refs; `produces: []` = no outputs. (dataflow)
- **`rundir:`** — `unique`(default)/`inherit`. (tasks)
- **`iff:`** — conditional execution expression. (tasks, expressions, advanced)
- **`scope:`** — `root`/`export`/`local` (string or list). (visibility)
- **`tags:`** — e.g. `std.ResourceTag`. (resource_tags)
- **`uptodate:`** — `false` / Python method / empty. (incremental, advanced)
- **`max_failures:`** — `-1`(default no-limit)/`0`(fail-fast)/`N`. (tasks, error_handling)
- **`on_error:`** — `module.function` aggregation callable. (tasks, error_handling)
- **`cache:`** (CacheDef) — referenced as a schema def. (flow_spec)
- **`desc:`** / **`doc:`** — description/documentation fields. (dataflow)

### Types / params
- **`types:`** — `name`, `uses`, `doc`, `with` fields. Param types: bool/int/list/map/str. (concepts, types_api, parameters)
- ComplexType / ListType / MapType schema defs. (flow_spec)
- DataItem tasks: a task that `uses:` a data type (produces a data item, no code). (tasks, types_api)

### Overrides (package-level)
- **`overrides:`** with `for:`/`use:` (parameter override) and `task:`/`with:` (task/param override) and `override:`/`with:` forms. (parameters, packages, stdlib)
- Resolution precedence documented (external > root pkg > non-root pkg > outer task > inner task > base). (parameters)

### Schema reference (flow_spec.rst lists generated jsonschema defs)
- PackageDef, FragmentDef, ConfigDef, PackageImportSpec, OverrideDef, ExtendDef, TaskDef, StrategyDef, GenerateSpec, CacheDef, ParamDef, TypeDef, ComplexType, ListType, MapType, ConsumesE, PassthroughE, RundirE, CompressionType. (flow_spec)

---

## 3. Task implementation mechanisms

- **Shell-script tasks** — `run:` body + `shell: bash` (default). `${{ }}` substitution; `${{ rundir }}`, `${{ srcdir }}`, `${{ this.<param> }}`. (developing_tasks, stdlib)
- **Inline pytask** — `shell: pytask` with inline `run:` body; evaluated as async method body with `ctxt`, `input`. (developing_tasks)
- **External pytask** — `shell: pytask`, `run: pkg.module.MethodName`; async `def MyTask(ctxt, input)`. (developing_tasks)
- **PyTask class API** — dataclass subclass of `dv_flow.mgr.PyTask`; nested `Params` dataclass; `async def __call__(self)`; `self.params`, `self._ctxt`, `self._input`; can return command string or None; class attrs `desc`/`doc`/`shell`. (python_tasks, python_api)
- **PyPkg package factory** — `dv_flow.mgr.PyPkg` subclass + `@pypkg(Pkg)` decorator; `registerTask`; tasks become `pkg.Task`. **[partly FORWARD-LOOKING — described as "advanced feature"]** (python_tasks, python_api)
- **Plugin packages** — Python entry-point group `dv_flow.mgr`; `dfm_packages()` returns `{name: flow.yaml path}`. (packages)
- **Task-graph generation** — `strategy.generate` with generator method `def GenGraph(ctxt, input)` using `ctxt.mkTaskNode`, `ctxt.mkName`, `ctxt.addTask`. (developing_tasks, advanced, python_api)
- **Custom up-to-date method** — async `def check(ctxt: UpToDateCtxt) -> bool`. (incremental, python_api, advanced)
- **`run_subgraph(tasks, max_failures=...)`** — dynamic subgraph from Python with failure control. (error_handling, developing_tasks, python_api)

---

## 4. Script ↔ Dataflow I/O contract (guide/script_io.rst, guide/developing_tasks.rst)

### Inputs (env vars the runner sets)
- **`DFM_RUNDIR`** (alias `TASK_RUNDIR`) — run dir.
- **`DFM_SRCDIR`** (alias `TASK_SRCDIR`) — source dir.
- **`DFM_TASK_NAME`** — fully-qualified task name.
- **`DFM_PARAM_<NAME>`** — each declared param (scalars verbatim; list/map compact JSON; bool `true`/`false`).
- **`DFM_PARAMS`** — path to JSON of all params.
- **`DFM_INPUTS`** — path to JSON array of consumed input items.
- **`DFM_MEMENTO`** — path to prior memento JSON (absent first run).

### Outputs (append-only files)
- **`DFM_OUTPUT`** — JSONL data items → `output` (FileSet `basedir:"."` rewritten to rundir).
- **`DFM_ENV`** — `KEY=VALUE` (+ heredoc) → `std.Env` `vals`.
- **`DFM_PATH`** — one dir per line → `std.Env` `prepend_path`.
- **`DFM_MARKERS`** — JSONL `{severity,msg,loc?}` → markers.
- **`DFM_MEMENTO_OUT`** — JSON object → memento for next run.
- exit code → `status` (authoritative; markers never flip it).

### `dfm-out` helper (console script on PATH)
- Subcommands: **`dfm-out fileset --filetype <t> <files...>`**, **`env KEY=VAL`**, **`path <dir>`**, **`error "<msg>" --file --line`**, **`item --type <T> key=val n:=3`** (`:=` = JSON-typed value).
- Fallback: **`python -m dv_flow.mgr.out`**; or raw `echo >> "$DFM_OUTPUT"`.
- GitHub-Actions mapping table: `$GITHUB_OUTPUT`→`$DFM_OUTPUT`, `$GITHUB_ENV`→`$DFM_ENV`, `$GITHUB_PATH`→`$DFM_PATH`, `INPUT_<NAME>`→`DFM_PARAM_<NAME>`, `$GITHUB_STEP_SUMMARY`→`$DFM_MARKERS`.
- **[FORWARD-LOOKING / deprecation]** `TASK_SRCDIR`/`TASK_RUNDIR` aliases "remain for one release and are then removed".

---

## 5. Standard library (std tasks/types/filters + Agent resources)

### std tasks (guide/stdlib.rst, guide/packages.rst)
- **std.FileSet** — params: type(req), base, include(req), exclude, incdirs, defines, attributes; produces `std.FileSet`; `consumes: none`.
- **std.CreateFile** — params: type(req), filename(req), content, incdir; produces single-file FileSet.
- **std.Message** — param msg; passthrough all; consumes all.
- **std.SetEnv** — params setenv, append_path, prepend_path; glob expansion; produces `std.Env`.
- **std.SetFileType** — param filetype; consumes `[{type: std.FileSet}]`.
- **std.IncDirs** — no params; extracts incdirs from filesets.
- **std.Null** — no-op passthrough; default override/stub replacement; `consumes: none`, `passthrough: all`.
- **std.TaskFailure** — framework-emitted item (task_name, status, markers). (error_handling, stdlib, python_api)
- **std.Agent** — runs AI assistant with prompt; params system_prompt, user_prompt, result_file (`{name}.result.json`), assistant (`copilot` default; **`openai`/`claude` "not yet implemented"** **[FORWARD-LOOKING]**), assistant_config. Required result JSON schema {status, changed, output, markers}. Debug files `{name}.prompt.txt`, `.result.json`, `assistant.stdout/stderr.log`. (stdlib)
- Shell commands: `shell: bash` + `run:` (also listed as a "task" mechanism). (packages, stdlib)

### std types (reference/types_api.rst)
- **std.DataItem** (base, field `type`), **std.FileSet** (filetype, basedir, files, incdirs, defines, attributes), **std.Env** (vals, append_path, prepend_path). Field types bool/int/list/map/str.
- **std.Tag** (base for tags), **std.ResourceTag** (cores, memory, queue, walltime, resource_class). (resource_tags, runner_config)

### Standard filters (guide/filters.rst, guide/stdlib.rst, guide/dataflow.rst)
- `by_filetype(ext)`, `by_type(typename)`, `basenames`, `extensions`, `paths`, `first_of_type(typename)`, `pluck(field)`, `count_by_type`.
- Custom filters: package `filters:` key, fields name/expr/run/shell/with(positional `$arg0…`)/export/local; default "name" visibility.

### Agent resources (ai/*, reference/cli.rst)
- **std.AgentSkill** — tag `std.AgentSkillTag`; fields `files`, `content`, `urls` (inherits `std.AgentResource`).
- **std.AgentPersona** — tag `std.AgentPersonaTag`; field `persona`/`desc`. (does NOT inherit AgentResource)
- **std.AgentTool** — tag `std.AgentToolTag`; fields `command`, `args`, `url`. MCP server integration **[FORWARD-LOOKING: "MCP integration currently in development"]**.
- **std.AgentReference** — tag `std.AgentReferenceTag`; fields files/content/urls.
- **std.AgentResource** — base providing `files`, `content`, `urls`.
- **Two skill-definition forms shown (INCONSISTENCY to verify):**
  - **Task form** (canonical per agent_resources/using_with_agents): a *task* `uses: std.AgentSkill` with `files:`/`content:`/`urls:` (often `local: AgentSkill`).
  - **DataSet/type form** (ai/using_with_agents "Skill Definition", overview): "skills defined as **DataSet types tagged with `std.AgentSkillTag`**"; and a `types:` entry `uses: std.AgentSkill` then a task that `uses:` that type. `dfm show skills` JSON shows `skill_name`, `is_default`.
  - overview.rst also references a `std.DataSet`-style `skill_doc` concept indirectly via "DataSet types tagged" — verify whether skills are types or tasks.

---

## 6. Execution / runtime

- **Runner backends** — `local` (default, in-process jobserver), `lsf`, `slurm` (**[FORWARD-LOOKING: "Placeholder for future SLURM support"]**). Third-party via `dfm_runners` entry point. (runners, runner_backend_api)
- **`RunnerBackend` / `LocalBackend`** autodoc API. (runner_backend_api)
- **Daemon** — `dfm daemon start/stop/status`, `--monitor`; state `<project>/.dfm/daemon.json`, socket `<project>/.dfm/daemon.sock`; auto-discovery from `dfm run --runner lsf`; multi-client; stale-file handling; top-style monitor TUI. (runners)
- **Worker pool** — config `pool.{min_workers,max_workers,idle_timeout,launch_batch_size}`. (runner_config)
- **Incremental / up-to-date** — `exec.json`/`exec_data.json` per task; checks: exec record, params, input changed flag, input structure, custom check. (incremental)
- **Memento system** — TaskDataResult `memento`, `input.memento`. (incremental)
- **exec.json / exec_data.json schema** — name, status, changed, params, inputs, outputs, memento, markers, exec_info, start/end_time, duration_ms. (incremental)
- **base-rundir** — satisfaction from saved exec_data.json with status 0; path rewriting; `(base)` suffix with `--verbose`; read-only/trusted; `--force` overrides, `--clean` cleans only local. (cli, incremental)
- **Report bundle** (`--report DIR`) — layout `report.json`/`report.md`/`markers.jsonl`/`logs/<task>.log`; `report.json` schema `dvflow-report/1` (root, status=#failed, generated_unix, counts, tasks[]). Backend-agnostic, assembled from per-task `exec_data.json`. (cli, running)
- **Output directory structure** — top-level `cache/` and `log/`; per-task `<task>.exec_data.json` + logfiles; nested for compound. (cli)
- **Trace output** — Google Event Trace Format `log/<root_task>.trace.json`, Perfetto/Chrome. (cli, advanced)
- **UI modes** — log/progress/tui; auto-select by terminal. (cli, running)
- **Resource tags** — `std.ResourceTag` (cores/memory/queue/walltime/resource_class); LSF/SLURM consume, local ignores; resolution precedence; resource_classes from config. (resource_tags, runner_config)
- **Runner config hierarchy** — install (`<sys.prefix>/etc/dfm/config.yaml` or `DFM_INSTALL_CONFIG`) → site (`~/.config/dfm/site.yaml`) → project (`<project>/.dfm/config.yaml`) → CLI/env. Merge rules (last-writer-wins vs accumulated). (runners, runner_config)

---

## 7. Agent / LLM features

- **`dfm agent`** TUI — collects skills/personas/tools/references from referenced tasks, builds system prompt, launches assistant. Workflow steps documented. (cli, ai/agent_resources, ai/using_with_agents)
- **Native agent** — embedded, `openai-agents` + LiteLLM; default when no subprocess CLI found; `-a native`. Optional install `pip install dv-flow-mgr[agent]`. (native_agent, agent_resources)
- **Provider config** — model priority order (`-m` > config `model:` > `DFM_MODEL` > `DFM_PROVIDER` > API-key auto-detect > `github_copilot/gpt-4.1`). Providers: GitHub Copilot, OpenAI, Anthropic, Azure, Gemini, OpenAI-compatible, Ollama. (native_agent)
- **Agent config file** — `~/.dfm/agent.yaml` / `.dfm/agent.yaml`: `model`, `approval_mode {never,auto,write}`, `trace`/`trace_dir`, `system_prompt_extra`, `model_settings{api_base,api_key,api_version,ssl_verify,headers}`, `mcp_servers[]`. `${{ env.VAR }}` expansion. (native_agent)
- **Native agent TUI** — slash commands `/help /model /tools /skills /personas "/skill add" "/persona add" /cost /approval /clear /exit /quit`; Ctrl+D/Ctrl+C/arrows. (native_agent)
- **Native agent tools** — DFM tools: `dfm_show_tasks, dfm_show_task, dfm_show_packages, dfm_show_types, dfm_show_skills, dfm_context, dfm_validate, dfm_run_tasks`; coding tools: `shell_exec, write_file, apply_patch, read_file, list_directory, grep_search`. (native_agent)
- **Subprocess (legacy) agents** — `-a copilot`, `-a codex`; JSON result-file protocol; no streaming TUI. (native_agent, agent_resources)
- **`dfm context [--json]`** — full project context JSON (project, tasks, types, skills). (cli, ai/using_with_agents)
- **`dfm show skills [--json] [--package] [--search] [<name> --full]`** — lists skills (DataSet types tagged `std.AgentSkillTag`). (ai/using_with_agents)
- **`dfm --help` skill path** — prints absolute path to bundled `skill.md` (`.../dv_flow/mgr/share/skill.md`). (ai/using_with_agents)
- **AGENTS.md** — auto-discovered project file orienting external agents. (ai/using_with_agents)
- **Server mode** — `dfm run` opens Unix socket at `DFM_SERVER_SOCKET`; child `dfm` runs in client mode; commands `run/show/context/validate/ping`; JSON success/error responses. (ai/using_with_agents)
- **MCP** — AgentTool/MCP servers; `mcp_servers` config; **[FORWARD-LOOKING: "MCP integration currently in development … may not be fully functional"]**. (agent_resources, native_agent)
- **std.Agent task** (also §5) — AI-in-the-loop task producing result JSON. (stdlib)

---

## 8. Expressions, filters, visibility, error handling

### Expressions (guide/expressions.rst, guide/concepts.rst)
- **`${{ }}`** syntax; evaluated during graph elaboration (static) or deferred at runtime.
- References: package params, task params, parent compound params, `matrix.<var>`, `${{ params.<name> }}`, `${{ this.<param> }}`, `$var` explicit prefix.
- Operators: arithmetic `+ - * / // % **`, comparison `== != < <= > >=`, logical `and or not`.
- Conditional: Python ternary `x if cond else y`.
- Indexing/slicing: `arr[0]`, `arr[:3]`, `arr[2:]`, `config['k']`, `obj.field`, `items[]` iteration.
- Built-in functions: `len, str, int, bool`.
- Runtime/deferred vars: **`inputs`**, **`memento`** (auto-deferred). `env.VAR` (agent config).
- **JQ-style builtins** (pipe `|`): `length, keys, values, sort, unique, reverse, first, last, flatten, type, split(sep)`; chaining.
- Limitations: no side effects/IO/arbitrary code; `map()`/`select()` arg-eval limitation; explicit `input` (no implicit `.`); **negative indices unsupported**. (filters)
- Evaluation order: package load → task elaboration → `iff` → matrix expansion. (expressions)

### Filters (guide/filters.rst, guide/dataflow.rst, guide/stdlib.rst)
- Pipe operator `|`; std filters (see §5); custom `filters:` definitions; `expr` vs `run`/`shell`; positional args `$arg0…`; visibility export/local/name; qualified `pkg.filter`.

### Visibility (guide/visibility.rst)
- Scopes: **root** (entry point, listed), **export** (cross-package), **local** (declaration-context only), **(none)** = package visibility (warns cross-pkg).
- `scope:` field (string or list `[root, export]`); inline markers `root:`/`export:`/`local:`.
- Warning emitted when referencing non-export task from another package.
- Listing-behavior summary table (In Listing / Cross-Pkg / Direct Run).

### Error handling (guide/error_handling.rst, guide/tasks.rst, reference/python_api.rst)
- **`max_failures`** — `-1` default (no limit), `0` fail-fast, `N` stop after N. Scoping semantics differ for `N>0`.
- **`on_error`** — `module.function` async aggregator `(ctxt: TaskRunCtxt, input: CompoundRunInput) -> TaskDataResult`; called even with no failures.
- **Default aggregation** — OR-accumulate `std.TaskFailure.status`, pass other items through, consume TaskFailure.
- **std.TaskFailure** item (task_name, status, markers); propagates through skipped tasks.
- API types: **CompoundRunInput** (name, inputs, subtasks, params, rundir, srcdir, changed, memento), **SubtaskSummary** (name, status, skipped), **TaskFailure**.
- `ctxt.info/warning/error` markers. `run_subgraph(max_failures=)` parity.
- Dataflow validation warnings vs errors (dfm validate): consumes/produces subset/OR matching. (dataflow, cli)

---

## Python API surface referenced (reference/python_api.rst, reference/types_api.rst)
- Classes (autodoc): `TaskDataInput`, `TaskDataItem`, `TaskRunCtxt`, `TaskDataResult`, `TaskMarker`, `TaskMarkerLoc`, `TaskGenCtxt`, `TaskGenInputData`, `UpToDateCtxt`, `PyTask`, `PyPkg`, `RunnerBackend`, `LocalBackend`, `ExecCmd`, `Type`, `TypeField`, `TypeDef`.
- `TaskRunCtxt` methods: `mkDataItem`, `exec`, `exec_parallel(ExecCmd[])`, `error/warning/info`, `run_subgraph`; props `rundir`, `root_pkgdir`, `root_rundir`, `env`.
- `TaskGenCtxt` methods: `mkTaskNode`, `mkName`, `addTask`; props rundir/srcdir/basename/input/builder.
- `UpToDateCtxt`: `exec()`, `exec_data`, `rundir`, `memento`, `params`, `srcdir`.

---

## Specific claims to verify (names / syntax)

### Command names
`dfm run`, `dfm show`, `dfm show packages|tasks|task|types|tags|package|project|skills`, `dfm agent`, `dfm context`, `dfm graph`, `dfm validate`, `dfm util`, `dfm daemon start|stop|status`, `dfm daemon --monitor`, `dfm ping`, `dfm-out`, `python -m dv_flow.mgr.out`.

### Flag names
`-D`, `-P`, `--package-map`, `-c/--config`, `--root`, `--log-level`, `-j`, `--clean`, `-f/--force`, `-v/--verbose`, `-u/--ui {log,progress,tui}`, `--override`, `--runner`, `--runner-opt`, `--base-rundir`, `--report`, `--timeout`, `--search`, `--regex`, `--tag`, `--json`, `--package`, `--scope`, `--produces`, `--needs`, `--tags-only`, `--data-items-only`, `--imports`, `--configs`, `--full`, `-a/--assistant {copilot,codex,mock,native}`, `-m/--model`, `--config-file`, `--approval-mode`, `--trace`, `-f/--format {dot}`, `-o/--output`, `--pool-size`, `--monitor`, legacy `-a` (show dependency tree).

### Task/flow field names
`package`, `fragment`, `name`, `root`, `export`, `local`, `override`, `uses`, `type`, `needs`, `feeds`, `with`, `append`, `prepend`, `run`, `shell`, `body`, `strategy.matrix`, `strategy.generate`, `template`, `extensions`, `extend`, `consumes`, `passthrough`, `produces`, `rundir` (`unique`/`inherit`), `iff`, `scope`, `tags`, `uptodate`, `max_failures`, `on_error`, `cache`, `desc`, `doc`, `configs`, `imports` (`name`/`from`/`as`), `package-map` (`version`/`packages`/`path`), `filters` (`expr`/`run`/`with`/`export`/`local`), `overrides` (`for`/`use`, `task`/`with`, `override`/`with`), `types` (`with`), param `type` values bool/int/list/map/str.

### std task / type / filter / agent names
`std.FileSet`, `std.CreateFile`, `std.Message`, `std.SetEnv`, `std.SetFileType`, `std.IncDirs`, `std.Null`, `std.Agent`, `std.TaskFailure`, `std.DataItem`, `std.Env`, `std.Tag`, `std.ResourceTag`, `std.AgentSkill`, `std.AgentPersona`, `std.AgentTool`, `std.AgentReference`, `std.AgentResource`, `std.AgentSkillTag`, `std.AgentPersonaTag`, `std.AgentToolTag`, `std.AgentReferenceTag`; filters `by_filetype`, `by_type`, `basenames`, `extensions`, `paths`, `first_of_type`, `pluck`, `count_by_type`; JQ builtins `length keys values sort unique reverse first last flatten type split`.

### Env-var names
`DV_FLOW_PACKAGE_MAP`, `DV_FLOW_PATH`, `DFM_BASE_RUNDIR`, `DFM_RUNNER`, `DFM_INSTALL_CONFIG`, `DFM_SERVER_SOCKET`, `DFM_MODEL`, `DFM_PROVIDER`; script-IO: `DFM_RUNDIR`, `DFM_SRCDIR`, `DFM_TASK_NAME`, `DFM_PARAM_<NAME>`, `DFM_PARAMS`, `DFM_INPUTS`, `DFM_MEMENTO`, `DFM_OUTPUT`, `DFM_ENV`, `DFM_PATH`, `DFM_MARKERS`, `DFM_MEMENTO_OUT`, aliases `TASK_RUNDIR`/`TASK_SRCDIR`; provider keys `GITHUB_TOKEN`, `OPENAI_API_KEY`, `OPENAI_API_BASE`, `ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, `GEMINI_API_KEY`, `OLLAMA_HOST`, `OLLAMA_API_BASE`.

### Python API names
`TaskRunCtxt`, `TaskDataInput`, `TaskDataItem`, `TaskDataResult`, `TaskMarker`, `TaskMarkerLoc`, `TaskGenCtxt`, `TaskGenInputData`, `UpToDateCtxt`, `CompoundRunInput`, `SubtaskSummary`, `TaskFailure`, `PyTask`, `PyPkg`, `@pypkg`, `RunnerBackend`, `LocalBackend`, `ExecCmd`, `Type`, `TypeField`, `TypeDef`; methods `mkDataItem`, `exec`, `exec_parallel`, `run_subgraph`, `mkTaskNode`, `mkName`, `addTask`, `registerTask`; entry points `dv_flow.mgr`, `dfm_runners`, `dfm_packages()`.

### Config-file paths
`~/.dfm/agent.yaml`, `.dfm/agent.yaml`, `<sys.prefix>/etc/dfm/config.yaml`, `~/.config/dfm/site.yaml`, `<project>/.dfm/config.yaml`, `<project>/.dfm/daemon.json`, `<project>/.dfm/daemon.sock`, bundled `dv_flow/mgr/share/skill.md`, schema `dv.flow.schema.json`.

### Notable discrepancies / things to scrutinize against code
- **`type:` vs `uses:`** — quickstart uses `type:` for both base-task and FileSet param; docs say both work.
- **`exec.json` vs `exec_data.json`** — incremental.rst uses `exec.json` in prose but `*.exec_data.json` elsewhere; verify actual filename.
- **Skill definition form inconsistency** — task-form (`uses: std.AgentSkill` + `files:`) vs type/DataSet-form ("DataSet types tagged with std.AgentSkillTag", `skill_name`, `is_default`). Verify which (or both) the code supports and the `dfm show skills` JSON fields.
- **`dfm agent --ui` values** — cli lists `{log,progress,tui}`; ai/using_with_agents lists `{log,progress,progressbar,tui}`.
- **imports `pkg:` key** — agent_resources uses `imports: - pkg: name` while packages.rst uses `name:`/`from:`/`as:`. Verify `pkg:` is valid.
- **std.Agent assistants** `openai`/`claude` marked "not yet implemented".
- **slurm** runner is a placeholder.
- **MCP** integration "in development".
- **PyPkg** described as advanced/possibly-aspirational.
