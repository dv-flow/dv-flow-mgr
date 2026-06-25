# Documentation Reorganization Design

**Status:** Proposal for review
**Date:** 2026-06-07 (rev. 2026-06-25 — fold in shell-script tasks + package maps)
**Scope:** `docs/**/*.rst` (Sphinx site)

---

> **Revision note (2026-06-25).** Since the first draft, two capabilities have
> landed that this reorg must account for:
>
> - **Shell-script task implementation is now a first-class way to author
>   tasks** (`run:` + `shell:` fields, with a `DFM_*`/`dfm-out` I/O contract
>   documented in `script_io.rst`). The docs should present *shell-script tasks
>   as the place to start*, with a Python task implementation introduced later
>   as the "when you outgrow shell" escalation. The current
>   `tasks_developing.rst` still opens Python-first; that framing is inverted
>   below (see §4.6).
> - **Package-map files** (`--package-map`, the `package-map:` flow-file key,
>   and `DV_FLOW_PACKAGE_MAP`) let projects import dependencies by name. This
>   touches `guide/packages.rst` and the CLI reference (see §4.7, §6).

---

## 1. Why this rework

The documentation has grown organically to **28 `.rst` files** and the
top-level table of contents is now a flat list that mixes tutorials, user
guide topics, API references, and CLI references at the same level. The
biggest pain points:

1. **No grouping in the root TOC.** `docs/index.rst` lists `quickstart`,
   `userguide/index`, `reference/index`, `reference/types_api`, `cmdref`,
   `llms`, `pytask_api`, and `task_runners` as siblings. A reader can't tell
   what is a guide, what is reference, or where to start.

2. **AI/agent content is fragmented across four files** (~2,600 lines) with
   heavy overlap:
   - `docs/llms.rst` — *"LLM Agent Integration"* (param overrides, skills,
     server mode, JSON discovery)
   - `docs/userguide/llm_integration.rst` — *"LLM Integration"* (AGENTS.md,
     custom skills)
   - `docs/userguide/agent_integration.rst` — *"AI Agent Integration"*
     (AgentSkill / Persona / Tool / Reference resource model)
   - `docs/userguide/native_agent.rst` — *"Native AI Agent (dfm agent)"*
     (provider config, TUI)

   "Skills" are documented in **three** of these. The three near-identical
   titles ("LLM Integration", "AI Agent Integration", "LLM Agent
   Integration") are impossible to disambiguate from a TOC.

3. **Runner content is split across four files** with two of them sharing the
   title *"Task Runners"*:
   - `docs/task_runners.rst` (29-line stub: intro + autoclass)
   - `docs/userguide/runners.rst` (selecting/configuring runners)
   - `docs/userguide/daemon.rst` (daemon required by remote runners)
   - `docs/reference/runner_config.rst` (config field reference)

4. **Reference material is split between two locations.** `docs/reference/`
   holds the flow-spec schema, `runner_config`, `resource_tags`, and
   `types_api`, while `cmdref.rst`, `pytask_api.rst`, and `task_runners.rst`
   sit loose at the top level. API docs (Python task API, type system API,
   runner autoclass) are intermixed with spec reference (flow.yaml schema)
   and CLI reference.

5. **The User Guide is a flat 19-item list** (`userguide/index.rst`) with no
   sub-grouping for concepts vs. authoring vs. execution vs. extending vs. AI.
   A newcomer has no reading order.

6. **CLI reference has drifted from the implementation.** The `dfm` CLI
   exposes `init`, `mcp`, `worker`, `daemon start|stop|status` (and top-level
   aliases `packages`, `tasks`, `task`, `types`, `tags`, `package`,
   `project`) — none of which appear in `cmdref.rst`. Parameter overrides
   (`-D` / `-P`) are documented in **both** `cmdref.rst` and `llms.rst`.

---

## 2. Design principles

- **Group by reader intent**, not by file age. Every page belongs to exactly
  one of five journeys: *Get started → Author flows → Run flows → Extend →
  Integrate with AI*, plus a *Reference* shelf.
- **One topic, one home.** Each subject (runners, skills, parameters) has a
  single canonical page; everything else links to it.
- **Separate "guide" prose from "reference" lookup.** Guides teach in reading
  order; reference pages are alphabetical/exhaustive lookups (schema, CLI,
  Python API).
- **Stable, descriptive, non-duplicated titles.** No two pages share a title.
- **Keep the directory shallow** — group via `toctree` captions, not deep
  nesting. Three content dirs: `guide/`, `ai/`, `reference/`.

---

## 3. Proposed structure

```
docs/
  index.rst                     ← landing page + grouped root toctree
  intro.rst              (NEW)  ← what DFM is, when to use it, mental model
  install.rst            (NEW)  ← split out of quickstart
  quickstart.rst                ← "your first flow" only

  guide/
    index.rst                   ← User Guide landing, grouped sub-toctrees
    # --- Core concepts ---
    concepts.rst                ← (was userguide/fundamentals.rst)
    packages.rst                ← (was userguide/packages.rst)
    tasks.rst                   ← (was userguide/tasks_using.rst) "Using Tasks"
    dataflow.rst                ← (was userguide/dataflow.rst)
    # --- Authoring flows ---
    parameters.rst              ← (was userguide/configuration.rst)
    expressions.rst             ← (was userguide/expressions.rst)
    filters.rst                 ← (was userguide/filters.rst)
    visibility.rst              ← (was userguide/visibility.rst)
    error_handling.rst          ← (was userguide/error_handling.rst)
    stdlib.rst                  ← (was userguide/stdlib.rst)
    # --- Running flows ---
    running.rst            (NEW)← CLI `dfm run` workflow, narrative
    incremental.rst             ← (was userguide/incremental.rst) caching/up-to-date
    runners.rst                 ← MERGE task_runners + userguide/runners + daemon
    # --- Extending DV Flow (start with shell, grow into Python) ---
    developing_tasks.rst        ← (was userguide/tasks_developing.rst)
                                   reframed shell-first: a shell-script task
                                   is the default/first-class implementation;
                                   Python is the "when you outgrow shell" path
    script_io.rst               ← (was userguide/script_io.rst)
                                   Script ↔ Dataflow I/O contract — the
                                   DFM_* env-var inputs + dfm-out outputs ABI
    python_tasks.rst            ← (was pytask_api.rst) authoring side
    advanced.rst                ← (was userguide/advanced_features.rst)

  ai/
    index.rst              (NEW)← AI & Agent Integration landing + audience map
    overview.rst           (NEW)← concepts + which-page-do-I-want decision guide
    using_with_agents.rst       ← MERGE llms.rst + userguide/llm_integration.rst
                                   (consume DFM from external LLM agents:
                                    AGENTS.md, JSON discovery, -D/-P, server)
    agent_resources.rst         ← (was userguide/agent_integration.rst)
                                   (authoring Skills/Personas/Tools/References)
    native_agent.rst            ← (was userguide/native_agent.rst) `dfm agent`

  reference/
    index.rst                   ← Reference landing, grouped sub-toctrees
    flow_spec.rst               ← (was reference/index.rst) flow.yaml schema
    cli.rst                     ← (was cmdref.rst) — refreshed to match CLI
    python_api.rst              ← (was pytask_api.rst) API-lookup side
    types_api.rst               ← (was reference/types_api.rst)
    runner_backend_api.rst      ← (was task_runners.rst) autoclass only
    runner_config.rst           ← (was reference/runner_config.rst)
    resource_tags.rst           ← (was reference/resource_tags.rst)
```

### Root `index.rst` toctree (grouped with captions)

```rst
.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   intro
   install
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   guide/index

.. toctree::
   :maxdepth: 2
   :caption: AI & Agent Integration

   ai/index

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference/index
```

### `guide/index.rst` — grouped sub-toctrees

```rst
.. toctree::
   :caption: Core Concepts
   concepts
   packages
   tasks
   dataflow

.. toctree::
   :caption: Authoring Flows
   parameters
   expressions
   filters
   visibility
   error_handling
   stdlib

.. toctree::
   :caption: Running Flows
   running
   incremental
   runners

.. toctree::
   :caption: Extending DV Flow
   developing_tasks
   script_io
   python_tasks
   advanced
```

---

## 4. Consolidations (the important changes)

### 4.1 AI / Agent: 4 files → 3 + landing

The four overlapping files are re-cut by **audience**, which is the real axis
they were confusing:

| New page | Audience / question it answers | Sources |
|---|---|---|
| `ai/overview.rst` | "What are DFM's AI capabilities and which page do I need?" | NEW (decision guide) |
| `ai/using_with_agents.rst` | "I drive DFM from an *external* coding agent (Claude/Copilot). How do I expose my project?" | `llms.rst` + `userguide/llm_integration.rst` |
| `ai/agent_resources.rst` | "I'm *authoring* a package and want to ship skills/personas/tools/references." | `userguide/agent_integration.rst` |
| `ai/native_agent.rst` | "I want to use DFM's *built-in* `dfm agent` TUI." | `userguide/native_agent.rst` |

Skill documentation is **deduplicated**: the canonical "how to define a skill"
content lives in `agent_resources.rst`; `using_with_agents.rst` keeps only the
*discovery* angle (`dfm show skills`, JSON output) and links across.

### 4.2 Runners: 4 files → 1 guide + 1 reference

- `guide/runners.rst` = narrative from `task_runners.rst` (intro) +
  `userguide/runners.rst` (selecting/configuring) + `userguide/daemon.rst`
  (the daemon section becomes a subsection, since the daemon exists to serve
  remote runners).
- `reference/runner_config.rst` stays as the field-level config reference.
- `reference/runner_backend_api.rst` holds the `RunnerBackend` / `LocalBackend`
  autoclass blocks (moved out of the old `task_runners.rst` stub).

### 4.3 Reference becomes a real section

All lookup-style material collects under `reference/`:
flow-spec schema, CLI, Python API, type-system API, runner backend API,
runner config, resource tags. The top level no longer carries loose
reference pages.

### 4.4 Python task content split by intent

`pytask_api.rst` currently serves both "how to write a Python task" (tutorial)
and "API surface" (lookup). **Decision: do the full split** (resolves §8 Q2):
- `guide/python_tasks.rst` — the authoring walkthrough (positioned as the
  "when you outgrow shell" escalation, per §4.6).
- `reference/python_api.rst` — the autodoc/API surface.

### 4.5 Quickstart split

`quickstart.rst` currently bundles installation + first flow. Split into
`install.rst` (pip, plugins like `dv-flow-libhdlsim`) and a focused
`quickstart.rst`. Add `intro.rst` as the conceptual landing ("packages,
tasks, dataflow" mental model — promoted from the prose currently buried in
`userguide/index.rst`).

### 4.6 Task authoring becomes shell-first

Implementing a task with a shell script (`run:` + optional `shell:`) is now the
**recommended starting point**, and the docs should lead with it. The Python
task implementation is the next step up — reached for when a script needs richer
control flow, typed data manipulation, or in-process access to DFM APIs.

- `guide/developing_tasks.rst` is **reframed shell-first**. The current opening
  ("it makes sense to provide a programming-language implementation for a task")
  is inverted: the chapter now teaches a shell-script task first (the `run:`
  body, the `shell:` selector, `${{ }}` substitution), shows how to exchange
  data with the graph, and only then says *"when a shell script gets unwieldy,
  graduate to a Python task."*
- `guide/script_io.rst` (moved from `userguide/script_io.rst`) is the canonical
  reference for the shell-task data contract: `DFM_*` env-var inputs
  (`DFM_RUNDIR`, `DFM_PARAMS`, `DFM_INPUTS`, …) and the append-only output
  channels (`DFM_OUTPUT`, `DFM_ENV`, `DFM_PATH`, `DFM_MARKERS`,
  `DFM_MEMENTO_OUT`) plus the `dfm-out` helper. `developing_tasks.rst` links
  here rather than restating the channel list.
- `guide/python_tasks.rst` keeps the Python authoring walkthrough but is now
  positioned as the escalation path, opening with a short "you've outgrown
  shell — here's the Python equivalent" framing that mirrors the shell example
  from `developing_tasks.rst`.

> This ordering must also be reflected wherever else the "how do I implement a
> task" question is answered first — notably the quickstart's first custom task
> and any `intro.rst`/`concepts.rst` mention of task implementations should show
> the shell form.

### 4.7 Package maps fold into Packages + CLI reference

Package maps (name → flow-file directories, consumed via the `package-map:`
flow-file key, the `--package-map` CLI flag, and `DV_FLOW_PACKAGE_MAP`) are an
authoring/resolution concern, so they live with packages — they do **not** get
their own top-level page:

- `guide/packages.rst` keeps its existing **Package Maps** section as the
  canonical narrative (what a map is, the file format, the three sources and
  their precedence, lazy import behavior).
- `reference/cli.rst` documents the `--package-map` global flag (see §6.1).
- `reference/flow_spec.rst` documents the `package-map:` package key (scalar or
  list) as part of the flow.yaml schema.

---

## 5. File-by-file disposition (complete map)

| Current file | Action | Destination |
|---|---|---|
| `index.rst` | Rewrite TOC w/ captions | `index.rst` |
| `quickstart.rst` | Split | `install.rst` + `quickstart.rst` + seed `intro.rst` |
| `cmdref.rst` | Move + refresh | `reference/cli.rst` |
| `llms.rst` | Merge | `ai/using_with_agents.rst` |
| `pytask_api.rst` | Split | `guide/python_tasks.rst` + `reference/python_api.rst` |
| `task_runners.rst` | Split | `guide/runners.rst` (prose) + `reference/runner_backend_api.rst` (autoclass) |
| `userguide/index.rst` | Rewrite as grouped landing | `guide/index.rst` |
| `userguide/fundamentals.rst` | Rename | `guide/concepts.rst` |
| `userguide/packages.rst` | Move (keeps Package Maps section, §4.7) | `guide/packages.rst` |
| `userguide/tasks_using.rst` | Move | `guide/tasks.rst` |
| `userguide/dataflow.rst` | Move | `guide/dataflow.rst` |
| `userguide/configuration.rst` | Rename | `guide/parameters.rst` |
| `userguide/expressions.rst` | Move | `guide/expressions.rst` |
| `userguide/filters.rst` | Move | `guide/filters.rst` |
| `userguide/visibility.rst` | Move | `guide/visibility.rst` |
| `userguide/error_handling.rst` | Move | `guide/error_handling.rst` |
| `userguide/stdlib.rst` | Move | `guide/stdlib.rst` |
| `userguide/incremental.rst` | Move | `guide/incremental.rst` |
| `userguide/runners.rst` | Merge | `guide/runners.rst` |
| `userguide/daemon.rst` | Merge (as subsection) | `guide/runners.rst` |
| `userguide/tasks_developing.rst` | Rename + reframe shell-first (§4.6) | `guide/developing_tasks.rst` |
| `userguide/script_io.rst` | Move | `guide/script_io.rst` (shell-task I/O contract) |
| `userguide/advanced_features.rst` | Rename | `guide/advanced.rst` |
| `userguide/llm_integration.rst` | Merge | `ai/using_with_agents.rst` |
| `userguide/agent_integration.rst` | Move | `ai/agent_resources.rst` |
| `userguide/native_agent.rst` | Move | `ai/native_agent.rst` |
| `reference/index.rst` | Rename + new landing | `reference/flow_spec.rst` (+ new `reference/index.rst`) |
| `reference/types_api.rst` | Move | `reference/types_api.rst` |
| `reference/runner_config.rst` | Keep | `reference/runner_config.rst` |
| `reference/resource_tags.rst` | Keep | `reference/resource_tags.rst` |
| — | NEW | `guide/running.rst` (narrative `dfm run` workflow) |
| — | NEW | `ai/index.rst`, `ai/overview.rst` |

---

## 6. Content fixes to fold in during the move

These are pre-existing accuracy gaps worth closing while files are touched:

1. **Refresh `reference/cli.rst`** to cover all current subcommands:
   `init`, `worker`, `daemon start|stop|status`, and the top-level
   query aliases (`packages`, `tasks`, `task`, `types`, `tags`, `package`,
   `project`). Also document the global `--package-map FILE` option (repeatable)
   and the `DV_FLOW_PACKAGE_MAP` environment variable. **Intentionally omit
   `dfm mcp`** — MCP is being de-emphasized (resolves §8 Q3), so it gets no CLI
   entry and no `ai/` page. Source of truth: `src/dv_flow/mgr/__main__.py`.
2. **De-duplicate `-D` / `-P` parameter overrides.** Make
   `guide/parameters.rst` canonical; `reference/cli.rst` and
   `ai/using_with_agents.rst` link to it instead of re-explaining.
3. **`type:` vs `uses:`** — the quickstart note about the dual meaning of
   `type` should point to a single canonical explanation in
   `guide/tasks.rst`.
4. **Fix toctree breakage** from moved paths (every `:doc:` cross-ref and
   `toctree` entry needs updating — Sphinx `make html` should build clean
   with zero warnings as the acceptance check).
5. **Invert the task-implementation narrative to shell-first** (§4.6). Audit
   the quickstart, `concepts.rst`, and `developing_tasks.rst` for any text or
   example that introduces a Python task before a shell-script task, and lead
   with the shell form throughout. Ensure `script_io.rst` is reachable from
   `developing_tasks.rst`.
6. **Document package maps** (§4.7) in `guide/packages.rst` (already present —
   verify it survives the move), `reference/cli.rst` (`--package-map`), and
   `reference/flow_spec.rst` (the `package-map:` key).

---

## 7. Suggested execution order (low-risk, incremental)

1. Create `guide/`, `ai/` dirs; move files with `git mv` (preserves history).
2. Update `toctree` entries + `:doc:` cross-references; get a clean
   `make html`.
3. Perform the AI/runner merges (the only content-editing steps).
4. Split quickstart and add `intro.rst` / `running.rst` / `ai/overview.rst`.
5. Refresh `reference/cli.rst` against `__main__.py` (incl. `--package-map`).
6. Reframe `developing_tasks.rst` shell-first and wire in `script_io.rst`
   (§4.6); verify package-map coverage (§4.7).
7. Switch the Sphinx theme to `furo` (§8.4): add `furo` to
   `docs/requirements.txt` and set `html_theme = "furo"` in `docs/conf.py`.

Steps 1–2 (and the theme swap in step 7) are pure mechanical reorg and can land
first for immediate navigational benefit; 3–6 are content work that can follow
in separate PRs.

---

## 8. Decisions (resolved during review)

These were open questions in the first draft; all are now settled.

1. **`guide/` vs keep `userguide/`?** → **Rename to `guide/`.** The site is
   pre-1.0; the clarity win outweighs breaking external deep links. (The
   structure and disposition map in §3/§5 already assume `guide/`.)
2. **Python task split (§4.4)** → **Full split.** `pytask_api.rst` becomes
   `guide/python_tasks.rst` (authoring walkthrough) + `reference/python_api.rst`
   (API surface). No single-page fallback.
3. **`dfm mcp` (MCP server) page?** → **Omit MCP from the docs.** MCP is being
   de-emphasized, so it gets neither an `ai/` page nor a `reference/cli.rst`
   entry (see §6.1). No action beyond *not* documenting it.
4. **Theme** (currently `alabaster`) → **Switch to `furo`.** Its left-sidebar
   nav makes the new caption grouping visible, and it's a well-maintained,
   low-config choice. Bundle the theme swap into this effort (add to
   `docs/conf.py` + `docs/requirements.txt`); it pairs naturally with the
   mechanical reorg in steps 1–2 of §7.

