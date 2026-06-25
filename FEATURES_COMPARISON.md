# Docs ↔ Implementation Reconciliation

Comparison of [`FEATURES_SRC.md`](FEATURES_SRC.md) (what the code does) against
[`FEATURES_DOCS.md`](FEATURES_DOCS.md) (what the docs claim). Every row below was
re-verified against the source.

Two questions:
- **A. Overlooked in the docs** — real, working features with no/!thin coverage.
- **B. Claimed but wrong** — docs assert something the code does not provide.

---

## A. Overlooked in the docs (features that exist but aren't documented)

| # | Feature | Evidence (src) | Doc status | Severity |
|---|---------|----------------|------------|----------|
| A1 | **Control-flow constructs** — `control:` with `type: if / match / while / do-while / repeat` (fields `cond`, `else`, `cases`, `when/default`, `until`, `max_iter`, `count`, `state`) | `task_def.py:116 ControlDef`; `task_node_{if,match,while,do_while,repeat}.py`; tests `tests/integration/test_control_flow_integration.py`, `tests/unit/test_task_node_control.py` | **✅ Addressed** — new dedicated page `guide/control_flow.rst` ("Conditional & Iterative Tasks") in Authoring Flows; cross-linked from `tasks.rst` (`iff` section). | ~~High~~ done |
| A2 | **Caching** — `dfm cache init [--shared]`, `DV_FLOW_CACHE` env var, provider-based artifact cache, per-task `cache:` semantics (compression, extra hash exprs) | `__main__.py:435 cache`; `cmd_run.py:243-248`; `cache_provider*.py`, `cache_config.py`; `task_def.py:289 CacheDef` | **✅ Addressed** — new dedicated page `guide/caching.rst` in Running Flows; cross-linked from `incremental.rst`; `dfm cache` auto-documented by the argparse directive. | ~~High~~ done |
| A3 | **`strategy.chain: true`** — run body tasks sequentially, each consuming the previous output | `task_def.py:63` | Not documented (docs cover `matrix`/`generate` only). | Medium |
| A4 | **`dfm complete`** — tab-completion candidate command | `__main__.py:228` | Not documented. | Low (internal-ish) |
| A5 | **`daemon start --foreground`** flag | `__main__.py:568` | `runners.rst` lists `--runner/--pool-size/--monitor` but not `--foreground`. | Low |
| A6 | **`shell`/`csh`/`tcsh` shells** | `ext_rgy.py:151-154` | Docs name `bash` and `pytask` but rarely list `shell`/`csh`/`tcsh` as valid. | Low |

> Auto-covered by the `.. argparse::` directive even if no prose exists:
> `dfm util`, `dfm worker`, the full daemon/agent option sets. Those are
> "documented" in the CLI reference by generation, so not listed as gaps.

---

## B. Claimed in the docs but NOT true in the code

| # | Doc claim | Page | Reality (src) | Fix |
|---|-----------|------|---------------|-----|
| B1 | `shell: sh` and `shell: python` are valid shells | `guide/stdlib.rst:152-156` | Only `shell`, `bash`, `csh`, `tcsh`, `pytask` are registered; `findShell` returns `None` for anything else (`ext_rgy.py:66-69,151-155`). `sh`/`python` would fail. | **Fixed** — list the real shells; Python is `pytask`. |
| B2 | Up-to-date data is stored in `exec.json` | `guide/incremental.rst:12,15,106,124` | The file is `<task>.exec_data.json` (`task_listener_report.py`, `cmd_run.py`; same page already uses `exec_data.json` at :287,:410). | **Fixed** — `exec.json` → `exec_data.json`. |
| B3 | Import a package with `imports: - pkg: <name>` | `ai/agent_resources.rst:286,602,742` | `PackageImportSpec` has no `pkg` key/alias; the import-by-name key is `name:` (aliases `from`/`as`/`config`/`with`) (`package_import_spec.py:50-67`). `pkg:` would be rejected (`extra="forbid"`). | **Fixed** — `pkg:` → `name:`. |
| B4 | "skills defined as **DataSet types** tagged with `std.AgentSkillTag`" | `ai/using_with_agents.rst:190` | Skills are `std.AgentSkill` → `std.AgentResource` → `std.DataItem` (not `DataSet`); discovered by the `AgentSkillTag` tag. Terminology is misleading. | **Fixed** — describe as items tagged `std.AgentSkillTag`. |
| B5 | `dfm agent -u {log,progress,tui}` | `reference/cli.rst`, `guide/running.rst` prose | The real choices include `progressbar` (`__main__.py:527,187`). The argparse auto-render is correct; only the hand-written prose is short. | Minor — left (prose simplification, not wrong per se). |
| B6 | AGENTS.md is "automatically discovered by AI assistants" | `ai/using_with_agents.rst:852` | True of *external* agents (an emerging convention), but **DFM itself has no AGENTS.md logic** (`src/` has zero references). The page presents it as the recommended DFM enablement path. | Note — defensible (it's an external-tool convention), but could clarify DFM doesn't read it. Left as-is pending a call. |

### Honestly-flagged forward-looking claims (already correct in docs)
These docs already mark the feature as not-yet-real, matching the code:
- **SLURM runner** — docs say "Placeholder for future SLURM support"; code raises `NotImplementedError` (`slurm_backend.py:35-45`). ✓
- **MCP integration** — docs say "currently in development"; code has a working `dfm mcp` stdio server but the native-agent MCP path is partial. ✓ (mild under-claim)
- **std.Agent `openai`/`claude` assistants** — docs say "not yet implemented"; code assistants are `copilot`/`codex`/`mock`/`native`. ✓
- **PyPkg** — docs call it an "advanced feature"; code is experimental (debug prints, hard-coded assumptions) (`pypkg.py`). ✓

---

## Summary

- **3 concrete false claims fixed** in this pass: `shell: sh|python` (B1),
  `exec.json` (B2), `imports: pkg:` (B3), plus a terminology fix (B4).
- **The 2 high-value gaps are now closed**: the `control:` construct family
  (A1) → `guide/control_flow.rst`, and caching (A2) → `guide/caching.rst` —
  both written from code-verified specs and wired into the nav. (Also,
  configurations were elevated from a buried section to a dedicated
  `guide/configurations.rst`.)
- **Remaining minor gaps** (low priority): `strategy.chain` (A3),
  `dfm complete` (A4), `daemon --foreground` (A5).
- Everything the docs flagged as "forward-looking" matches the code's actual
  partial/stub state — no over-claims there.
