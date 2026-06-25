# Documentation Reorganization — Implementation Plan

**Status:** In progress — structural reorg landed on branch `docs-reorg`
**Date:** 2026-06-25

## Execution status (2026-06-25)

| Phase | State |
|---|---|
| 0 — Baseline & branch | ✅ done (baseline 19 warnings) |
| 1 — Move files | ✅ done (all `git mv`; `userguide/` removed; imgs moved) |
| 2 — Toctrees & cross-refs | ✅ done |
| 3a — Runner merge | ✅ done (4→1 guide + 1 reference) |
| 3b — AI merge/dedup | ✅ done (`llm_integration.rst` merged into `using_with_agents.rst` + deleted; AI section now 3 pages) |
| 4 — Python split | ✅ done (`reference/python_api.rst` + `guide/python_tasks.rst` walkthrough) |
| 5 — New prose pages | ✅ done (intro, install, running, ai/overview, python_tasks) |
| 6 — `furo` theme | ✅ done (conf.py + ivpm.yaml both dep sets) |
| 7a — CLI refresh | ✅ done (argparse auto-covers subcommands + `--package-map`; added `DV_FLOW_PACKAGE_MAP` note; mcp not promoted) |
| 7b — `-D`/`-P` dedup | ✅ done (parameters.rst canonical; cli + using_with_agents link to it) |
| 7c — `type:`/`uses:` | ✅ done (canonical note in tasks.rst; quickstart points to it) |
| 7d — Shell-first reframe | ✅ done (`developing_tasks.rst` leads with shell tasks) |
| 7e — `flow.yaml` normalize | ✅ done (**zero** `flow.dv` in docs prose) |
| 7f — package-map schema | ✅ done (flow_spec renders PackageDef incl. `package-map`; cli documents the flag/env var) |

**All planned phases complete.** Full structural reorg + content merges +
new pages + accuracy pass all landed on branch `docs-reorg`, building under
`furo` with the four-group nav. 34 pages, no orphans.

**Build health: 19 → 1 warning.** The remaining warning is a bug *inside the
generated schema file* (`PackageDef` → non-existent `#/defs/PackageSpec` in
`src/dv_flow/mgr/share/dv.flow.schema.json`); it is a code-side fix, not a docs
issue. Fixes folded in along the way:
- **`reference/flow_spec.rst` schema directive repaired** — it pointed at a
  non-existent path (`../../schema/flow.dv.schema.json`) with obsolete
  kebab-case def names, producing 6 build ERRORs. Now points at the real
  `dv.flow.schema.json` and renders all 19 PascalCase defs (grouped: package
  structure / tasks / parameters & types / enumerations).
- RST title under/overline lengths fixed (native_agent, dataflow, types_api,
  llm_integration); stray transition removed in using_with_agents; created
  `docs/_static/`; fixed quickstart `emphasize-lines` (8,12 → 6,8); reflowed a
  `task_run_ctxt.py` docstring line that broke autodoc.

**What remains:** AI dedup merge (§3b), new prose pages (§5), CLI refresh
(§7a), parameter-override dedup (§7b), `type:`/`uses:` canonicalization (§7c),
package-map schema doc (§7f). Nothing committed yet.
**Source design:** [`DOCS_REORG_DESIGN.md`](DOCS_REORG_DESIGN.md)
**Scope:** `docs/**/*.rst`, `docs/conf.py`, `ivpm.yaml`

This is the actionable, trackable companion to the design. It breaks the reorg
into ordered phases of checkbox steps. Each phase ends with a **verification**
gate. The global acceptance check is a clean `make html` (zero warnings) plus a
spot-check of the rendered nav.

**How to track:** check boxes as steps land. Phases 1–2 (mechanical reorg) and
Phase 6 (theme) can ship as one PR for immediate navigational benefit; Phases
3–5 (content edits) and Phase 7 (shell-first + package maps) can follow in
separate PRs.

---

## Conventions

- Use `git mv` for every move/rename so history is preserved.
- After every batch of moves, fix `toctree` entries and `:doc:`/`:ref:`
  cross-references, then rebuild. Never let `make html` accumulate warnings.
- Build command (from `docs/`): `make html`. Treat any warning as a failure.
- Source of truth for the CLI reference: `src/dv_flow/mgr/__main__.py`.
- **Filename convention:** always write the flow-spec filename as **`flow.yaml`**
  — never `flow.dv`. This applies to all prose, example snippets, and command
  lines in the docs.

---

## Phase 0 — Baseline & safety net  ✅ DONE

- [x] Confirm a clean starting build: baseline = **19 warnings/errors**. Most
      are pre-existing and unrelated to the reorg (missing `_static`, schema
      relative-import errors in the old `reference/index.rst`, several title
      under/overline issues, a broken `pytask_api` ref in incremental.rst).
      Adjusted target: **introduce no new warnings**, and fix the move-related
      ones we touch.
- [x] Create a working branch: `git checkout -b docs-reorg`.
- [x] Inventoried all 44 `:doc:` cross-references + toctrees (saved during
      execution; mapping applied in Phase 2).

**Verification:** baseline build captured (19); branch `docs-reorg` created.

> **Execution decision:** a moves-only intermediate leaves the merge-donor files
> (`userguide/runners`, `daemon`, `llm_integration`) orphaned → broken build.
> So Phases **1–4 + 6** are executed together to reach a clean, reviewable
> build. The brand-new prose pages (Phase 5: `intro`, `install`, `running`,
> `ai/overview`) and content rewrites (Phase 7) are deferred; deferred pages are
> kept **out of the toctrees** for now so no empty placeholders publish.

---

## Phase 1 — Create the new tree & move files (mechanical)

Pure `git mv` + new empty/seed files. No prose edits yet (those are Phases 3–5,
7). After this phase the build *will* warn about broken toctrees — Phase 2
fixes them.

### 1a. New directories

- [x] `mkdir docs/guide docs/ai` (the `reference/` dir already exists).

### 1b. Top-level moves & renames

- [x] `git mv docs/cmdref.rst docs/reference/cli.rst`
- [x] `git mv docs/llms.rst docs/ai/using_with_agents.rst`
- [x] `git mv docs/reference/index.rst docs/reference/flow_spec.rst`
- [x] `git mv docs/task_runners.rst docs/guide/runners.rst`  *(prose lands here;
      autoclass blocks get extracted to `reference/runner_backend_api.rst` in
      Phase 3)*
- [x] `git mv docs/pytask_api.rst docs/guide/python_tasks.rst`  *(the
      reference/API half is split out in Phase 4)*

### 1c. userguide → guide moves

- [x] `git mv docs/userguide/fundamentals.rst docs/guide/concepts.rst`
- [x] `git mv docs/userguide/packages.rst docs/guide/packages.rst`
- [x] `git mv docs/userguide/tasks_using.rst docs/guide/tasks.rst`
- [x] `git mv docs/userguide/dataflow.rst docs/guide/dataflow.rst`
- [x] `git mv docs/userguide/configuration.rst docs/guide/parameters.rst`
- [x] `git mv docs/userguide/expressions.rst docs/guide/expressions.rst`
- [x] `git mv docs/userguide/filters.rst docs/guide/filters.rst`
- [x] `git mv docs/userguide/visibility.rst docs/guide/visibility.rst`
- [x] `git mv docs/userguide/error_handling.rst docs/guide/error_handling.rst`
- [x] `git mv docs/userguide/stdlib.rst docs/guide/stdlib.rst`
- [x] `git mv docs/userguide/incremental.rst docs/guide/incremental.rst`
- [x] `git mv docs/userguide/tasks_developing.rst docs/guide/developing_tasks.rst`
- [x] `git mv docs/userguide/script_io.rst docs/guide/script_io.rst`
- [x] `git mv docs/userguide/advanced_features.rst docs/guide/advanced.rst`

### 1d. userguide → ai moves

- [x] `git mv docs/userguide/agent_integration.rst docs/ai/agent_resources.rst`
- [x] `git mv docs/userguide/native_agent.rst docs/ai/native_agent.rst`

### 1e. Files merged in later phases (move the "primary", keep the donor for now)

- [x] `git mv docs/userguide/index.rst docs/guide/index.rst`  *(rewritten in
      Phase 2 as the grouped landing)*
- [x] `runners.rst` + `daemon.rst` **merged** into `guide/runners.rst` then
      `git rm`'d (Phase 3a). `llm_integration.rst` **moved** to
      `ai/llm_integration.rst` as an interim page (Phase 3b merge deferred).
      `userguide/` is now removed entirely. Images moved to `guide/imgs/`.

### 1f. New files created (full landing content, not stubs)

- [x] `docs/ai/index.rst` — AI landing + audience map + toctree.
- [x] `docs/reference/index.rst` — Reference landing + grouped toctree.
- [x] `docs/reference/python_api.rst` — created via Phase 4 split (the API
      surface from `pytask_api.rst`).
- [x] `docs/reference/runner_backend_api.rst` — created via Phase 3a (autoclass
      blocks extracted from the old `task_runners.rst`).
- [ ] `docs/intro.rst` — **deferred to Phase 5** (kept out of toctree).
- [ ] `docs/install.rst` — **deferred to Phase 5** (kept out of toctree).
- [ ] `docs/guide/running.rst` — **deferred to Phase 5** (kept out of toctree).
- [ ] `docs/ai/overview.rst` — **deferred to Phase 5** (kept out of toctree).
- [ ] `docs/guide/python_tasks.rst` (authoring walkthrough) — **deferred to
      Phase 5** (new prose; the API half already split to `reference/python_api`).

**Verification:** ✅ `git status` shows clean renames; `userguide/` removed.

---

## Phase 2 — Wire up toctrees & cross-references (mechanical)  ✅ DONE

Goal: a **clean `make html`** with the new structure, before any content
editing.

- [x] Rewrote `docs/index.rst` root toctree with the four captions (Getting
      Started / User Guide / AI & Agent Integration / Reference). *Getting
      Started lists only `quickstart` for now; `intro`/`install` join in Phase 5.*
- [x] Wrote `docs/guide/index.rst` grouped sub-toctrees (Core Concepts /
      Authoring Flows / Running Flows / Extending DV Flow). Extending order:
      `developing_tasks`, `script_io`, `advanced` (`python_tasks` walkthrough
      deferred to Phase 5; `running` deferred from Running Flows).
- [x] Wrote `docs/ai/index.rst` toctree: `using_with_agents`, `llm_integration`
      (interim), `agent_resources`, `native_agent` (`overview` deferred).
- [x] Wrote `docs/reference/index.rst` toctree: `flow_spec`, `cli`,
      `python_api`, `types_api`, `runner_backend_api`, `runner_config`,
      `resource_tags`.
- [x] Updated all 16 cross-references (renamed targets + absolute `/...` paths
      for cross-dir refs). Verified zero stale refs to old names.
- [x] Fixed image paths: moved `userguide/imgs/` → `guide/imgs/`; `cli.rst`
      perfetto image → `/imgs/...` absolute.
- [x] `make clean && make html` → **16 warnings, all pre-existing** (baseline
      was 19; the 3 reorg-related warnings — 2 orphaned-toctree + 1 broken
      `pytask_api` ref — are **eliminated**). **No new warnings introduced.**

**Verification:** ✅ build clean of reorg warnings; furo sidebar renders all
four caption groups + guide sub-captions.

> **Remaining 16 warnings are all pre-existing** (not caused by the reorg):
> missing `_static` dir; `flow_spec.rst` jsonschema relative-import errors (×6);
> several RST title under/overline length issues; a `code-block` error in
> `developing_tasks.rst:28`; an autodoc docstring indentation error in
> `task_run_ctxt.py`; a `quickstart` emphasize-lines range. These are tracked
> for a separate content/polish pass (not part of the structural reorg).

---

## Phase 3 — Content merges (runners + AI)

These are the only steps that combine multiple source files.

### 3a. Runners: 4 → 1 guide + 1 reference  ✅ DONE

- [x] Merged `userguide/runners.rst` (selecting/configuring) into
      `guide/runners.rst` and added `userguide/daemon.rst` as a **"Daemon"
      subsection** (H2, with H3 sub-headings).
- [x] Extracted the `RunnerBackend` / `LocalBackend` `autoclass` blocks into
      `reference/runner_backend_api.rst`.
- [x] `git rm docs/userguide/runners.rst docs/userguide/daemon.rst`.
- [x] `reference/runner_config.rst` unchanged; linked from `guide/runners.rst`
      and `reference/runner_backend_api.rst`.

### 3b. AI: external-agent merge + dedup  ✅ DONE

- [x] Merged `llm_integration.rst`'s unique content (Why-enable, **Creating
      AGENTS.md** template + best practices, Verifying Agent Compatibility,
      Complete Project Setup) into `using_with_agents.rst` as the "Enabling LLM
      Support in Your Project" section (replacing the old stub that just linked
      out).
- [x] Kept only the **discovery** angle for skills in `using_with_agents.rst`;
      replaced its stale "Skill Definition" block with a pointer to
      `agent_resources.rst`.
- [x] `git rm docs/ai/llm_integration.rst`; removed from `ai/index.rst`; fixed
      the two dangling cross-refs (agent_resources, native_agent) to point at
      `using_with_agents`.
- [x] `agent_resources.rst` confirmed canonical for Skills/Personas/Tools/
      References authoring.
- [x] **Omit MCP** (design §8.3): no `ai/` page documents `dfm mcp`; none created.
- [x] Retitled the page "Using DFM with External Agents" (was "LLM Agent
      Integration") to disambiguate from `agent_resources`' "AI Agent
      Integration".

> ⚠️ **Found a stale skill API while merging.** Both old AI pages documented
> skills as a ``std.DataSet`` type tagged ``std.AgentSkillTag`` with inline
> ``skill_doc``/``name``/``examples`` fields. The **current** std library
> (`src/dv_flow/mgr/std/flow.dv`) defines a skill as ``std.AgentSkill`` (→
> ``std.AgentResource``) with ``files``/``content``/``urls`` fields, documented
> correctly in `agent_resources.rst`. The merge **drops** the stale API and
> uses the correct one throughout. (Worth a follow-up audit of any other docs
> or examples still showing the old form.)

**Verification:** ✅ `make html` clean (1 schema-source warning only); AI
section is 3 pages; skill definition has a single canonical home.

---

## Phase 4 — Python task split (design §4.4 / §8.2)  ✅ DONE

- [x] `reference/python_api.rst` = the **autodoc/API surface** (the old
      `pytask_api.rst` is essentially all API reference, so it became this page).
- [x] `guide/python_tasks.rst` = the **authoring walkthrough**, opened with the
      "when you outgrow shell" escalation framing. Built by moving the
      class-based `PyTask` + `PyPkg` sections out of `developing_tasks.rst`
      (which keeps the shell-first intro + basic pytask and links onward).
- [x] Cross-linked: `developing_tasks.rst` → `python_tasks.rst` →
      `reference/python_api.rst` cross-reference each other.)*

**Verification:** ✅ both pages build; no duplicated autodoc.

---

## Phase 5 — New landing/intro content  ✅ DONE

- [x] `docs/intro.rst` — what DFM is, when to use it, and the packages / tasks /
      dataflow mental model (with a clean example; the buggy inline example that
      was in the old `userguide/index.rst` was rewritten, not copied).
- [x] `docs/install.rst` — installation split out of `quickstart.rst` (pip +
      plug-ins like `dv-flow-libhdlsim`); quickstart now links to it.
- [x] `docs/quickstart.rst` — trimmed to "your first flow"; the install section
      moved out.
- [x] `docs/guide/running.rst` — narrative `dfm run` workflow.
- [x] `docs/ai/overview.rst` — capabilities + "which AI page do I want?"
      decision table.
- [x] `docs/ai/index.rst` — AI landing + audience map. *(Done in Phase 2.)*
- [x] Trimmed the duplicated mental-model prose from `guide/index.rst` (now in
      `intro.rst`); the guide landing is a clean grouped TOC + orientation.

**Verification:** ✅ Getting-Started reads intro → install → quickstart;
`make html` clean; no orphan pages.

---

## Phase 6 — Theme swap to `furo` (design §8.4)  ✅ DONE

- [x] Added `furo` to **both** dependency sets in `ivpm.yaml` (`default` and
      `default-dev-all`, after `sphinxcontrib-mermaid`).
- [x] In `docs/conf.py`, changed `html_theme = 'alabaster'` → `'furo'`.
- [x] Installed `furo` into the docs env and `make clean && make html` —
      builds with `furo.css`/`furo-main-content` present, no theme warnings.
- [x] Confirmed the rendered sidebar shows all four caption groups (Getting
      Started, User Guide, AI & Agent Integration, Reference).

**Verification:** ✅ site renders with `furo` left-nav; build clean.

---

## Phase 7 — Accuracy fixes folded in (design §6)

### 7a. CLI reference refresh (`reference/cli.rst`)

- [ ] Document all current subcommands from `__main__.py`: `init`, `worker`,
      `daemon start|stop|status`, and top-level query aliases (`packages`,
      `tasks`, `task`, `types`, `tags`, `package`, `project`).
- [ ] Document the global `--package-map FILE` option (repeatable) and the
      `DV_FLOW_PACKAGE_MAP` environment variable.
- [ ] **Intentionally omit `dfm mcp`** (design §8.3).

### 7b. Parameter-override dedup

- [ ] Make `guide/parameters.rst` the canonical `-D`/`-P` explanation;
      `reference/cli.rst` and `ai/using_with_agents.rst` link to it instead of
      re-explaining.

### 7c. `type:` vs `uses:`

- [ ] Point the quickstart note about the dual meaning of `type` to a single
      canonical explanation in `guide/tasks.rst`.

### 7d. Shell-first task narrative (design §4.6)

- [ ] Reframe `guide/developing_tasks.rst` shell-first: teach the shell-script
      task (`run:` body, `shell:` selector, `${{ }}` substitution) **first**,
      then say "graduate to a Python task" for richer control flow. Invert the
      current Python-first opening.
- [ ] Ensure `guide/script_io.rst` (the `DFM_*` / `dfm-out` contract) is linked
      from `developing_tasks.rst` rather than restated.
- [ ] Audit `quickstart.rst`, `guide/concepts.rst`, and `intro.rst` for any
      example that introduces a Python task before a shell task; lead with shell.

### 7e. Normalize flow-spec filename to `flow.yaml`

- [ ] Sweep all moved/merged/new docs for `flow.dv` and replace with
      `flow.yaml` (prose, example snippets, command lines). Audit:
      `grep -rn 'flow\.dv' docs/`.
- [ ] Confirm zero `flow.dv` references remain in `docs/` after the sweep.

### 7f. Package maps (design §4.7)

- [ ] Verify `guide/packages.rst` retains its **Package Maps** section (file
      format, the three sources + precedence, lazy-import behavior).
- [ ] Document the `package-map:` package key (scalar or list) in
      `reference/flow_spec.rst`.
- [ ] (CLI `--package-map` already covered in 7a.)

**Verification:** `make html` clean; each fixed topic has exactly one canonical
home with cross-links pointing to it.

---

## Final acceptance checklist

- [x] `cd docs && make clean && make html` → **1 warning** (a generated-schema
      bug, not a docs issue; see note above). Down from 19 at baseline.
- [x] Root nav shows: Getting Started · User Guide · AI & Agent Integration ·
      Reference.
- [x] No two pages share a title; no orphaned pages (no "not in any toctree"
      warnings).
- [x] `userguide/` directory is gone.
- [x] Task-authoring path leads with shell scripts; Python is the escalation.
- [x] Package maps documented in packages + flow_spec + CLI.
- [x] `dfm mcp` is absent from the docs by design (no prose; only auto-listed by
      the argparse directive).
- [x] Theme is `furo`.
- [x] No `flow.dv` references remain in `docs/` — all use `flow.yaml`.

> **Known follow-ups (out of scope for the docs reorg):**
> 1. Fix the generated schema bug: `PackageDef` references `#/defs/PackageSpec`,
>    which is not defined in `src/dv_flow/mgr/share/dv.flow.schema.json` (fix in
>    the pydantic model that generates the schema).

### Non-doc audit (stale skill form + `flow.dv`) — ✅ DONE

Principle applied (per maintainer): **the loader keeps recognizing `flow.dv`
for back-compat; no user-facing string documents it** — including `--help`,
error messages, and shipped agent prompts/skill docs.

- **Stale skill form:** *no* non-doc occurrences. The only skill definition in
  code/tests (`tests/unit/test_show_skills.py:262`) already uses the canonical
  `uses: std.AgentSkill` + `files:` form. `skill_doc` in `collectors.py` /
  `cmd_show_skills.py` is the legitimate *resolved output* field (file content
  is read into it), not the stale definition form — left as-is.
- **`flow.dv` user-facing strings — fixed** (dropped `flow.dv`, kept the other
  recognized names): error messages and `--help` in `cmd_agent`, `__main__`,
  `util/util`, `cmd_run`, `cmd_graph`, `cmd_validate`, `cmd_context`; comments
  in `package_provider_yaml` / `task_exec_serialize`; shipped
  `share/prompts/copilot_system.md` and
  `share/skills/.../references/task_development.md`.
- **Kept (back-compat recognition):** the `("flow.dv","flow.yaml","flow.yml",
  "flow.toml")` filename tuples in `ext_rgy`, `package_provider_yaml`,
  `util/util`, `cmd_util`, and the `std/flow.dv` load path.
- All 198 affected unit tests pass; no test asserted on the old strings.

**Bundled std package renamed (approved):**
- `git mv src/dv_flow/mgr/std/flow.dv → std/flow.yaml`; updated the loader
  (`ext_rgy.py:148`) and the one test that reads it directly
  (`test_filter_integration.py`).
- Removed the tracked merge-leftover `src/dv_flow/mgr/std/flow.dv.orig`.
- Also renamed `std/filters.dv → std/filters.yaml` (the fragment that
  `std/flow.yaml` includes); updated the `fragments:` reference in `flow.yaml`,
  the file's header comment, and `test_filter_integration.py`.
- Added `std/*.yaml` to `[tool.setuptools.package-data]` so the std flow files
  ship in the wheel (`package-data` previously only globbed `share/**`).
- **1071 unit + system + filter-integration tests pass.** The installed
  site-packages copy is an older self-consistent build and refreshes on
  rebuild; tests use `PYTHONPATH=src`. The `std/` directory now contains **no
  `.dv` files** — fully migrated to `.yaml`.

---

## Disposition quick-reference (from design §5)

| Current | Action | Destination |
|---|---|---|
| `index.rst` | Rewrite TOC | `index.rst` |
| `quickstart.rst` | Split | `install.rst` + `quickstart.rst` + seed `intro.rst` |
| `cmdref.rst` | Move + refresh | `reference/cli.rst` |
| `llms.rst` | Merge | `ai/using_with_agents.rst` |
| `pytask_api.rst` | Split | `guide/python_tasks.rst` + `reference/python_api.rst` |
| `task_runners.rst` | Split | `guide/runners.rst` + `reference/runner_backend_api.rst` |
| `userguide/index.rst` | Rewrite | `guide/index.rst` |
| `userguide/fundamentals.rst` | Rename | `guide/concepts.rst` |
| `userguide/packages.rst` | Move (keep Package Maps) | `guide/packages.rst` |
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
| `userguide/daemon.rst` | Merge (subsection) | `guide/runners.rst` |
| `userguide/tasks_developing.rst` | Rename + reframe shell-first | `guide/developing_tasks.rst` |
| `userguide/script_io.rst` | Move | `guide/script_io.rst` |
| `userguide/advanced_features.rst` | Rename | `guide/advanced.rst` |
| `userguide/llm_integration.rst` | Merge | `ai/using_with_agents.rst` |
| `userguide/agent_integration.rst` | Move | `ai/agent_resources.rst` |
| `userguide/native_agent.rst` | Move | `ai/native_agent.rst` |
| `reference/index.rst` | Rename + new landing | `reference/flow_spec.rst` (+ new `reference/index.rst`) |
| `reference/types_api.rst` | Keep | `reference/types_api.rst` |
| `reference/runner_config.rst` | Keep | `reference/runner_config.rst` |
| `reference/resource_tags.rst` | Keep | `reference/resource_tags.rst` |
| — | NEW | `guide/running.rst` |
| — | NEW | `ai/index.rst`, `ai/overview.rst` |
| — | NEW | `reference/python_api.rst`, `reference/runner_backend_api.rst` |
