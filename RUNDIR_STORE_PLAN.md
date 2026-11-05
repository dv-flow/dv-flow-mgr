# Rundir Store — Implementation, Test and Doc Plan

Design: [RUNDIR_STORE_DESIGN.md](RUNDIR_STORE_DESIGN.md) (approved 2026-11-05).
Section references such as §6.4 point to the design doc.

This file tracks progress. Update the **Status** table and tick task boxes as
each step finishes. A fresh session should be able to resume from this file
alone.

Paths are relative to `src/dv_flow/mgr/` unless they start with `tests/`,
`docs/` or `pyproject.toml`.

## Status

| Phase | Title | State | Notes |
|---|---|---|---|
| 1 | Package-root rundir, symlink safety | done | |
| 2 | Config plumbing | done | shipped together with 3 |
| 3 | Store entries, `store info`/`init` | done | |
| 4 | `store list` / `gc` | done | |
| 5 | Rules, git context, Python SiteConfig | done | |
| 6 | `migrate`/`unlink`/`relink`, docs | done | |
| 7 | Statistics and cleanup reporting (design §8.3) | done | `stats`, `candidates`, richer `list`/`gc`/`info` |

**All phases are implemented (2026-11-05). Nothing has been committed.**
Unit suite: 2182 passed, 10 skipped, 5 xfailed. Integration and system:
82 passed, 4 skipped. See "Implementation notes" below for deviations from
the task lists.

### Files

New modules (under `src/dv_flow/mgr/`):
- `rundir_store.py`: `resolve_rundir`, `inspect_rundir`, `clean_rundir`,
  `find_pkg_root`, `create_entry`.
- `rundir_store_entry.py`: naming, metadata, lock, marker, classification,
  scan and size.
- `rundir_store_ops.py`: list/gc planning and execution, plus
  migrate/unlink/relink.
- `store_config.py`: `resolve_store`, rules and templates.
- `site_config.py`: `StoreContext`, `SiteConfig` and `SiteConfigRgy`.
- `config_paths.py`: install/site/user/project file locations; legacy
  `site.yaml`.
- `util/atomic.py`: `atomic_write_text`, `atomic_symlink`.
- `cmds/cmd_store.py` and `cmds/store/{common,cmd_info,cmd_init,cmd_list,cmd_gc,cmd_migrate,cmd_unlink,cmd_relink}.py`.
- `cmds/show/cmd_show_site_config.py`.

Changed:
- `__main__.py`: `_add_store_opts`, the `store` parser, and
  `show site-config`.
- `cmds/cmd_run.py`, `cmd_graph.py`, `cmd_agent.py`, `cmd_daemon.py`,
  `show/cmd_show_task.py`, `agent/tui.py`, `agent/context_builder.py`.
- `cmds/cmd_show.py`, `cmds/show/__init__.py`.
- `cache_util.py`: `_rel_to_rundir`.
- `task_runner.py`: `_rebase_path`.
- `util/util.py`: `find_root_flow_file` extracted.
- `runner_config.py`: now uses `config_paths` layers.
- `pyproject.toml`: commented entry-point example.

Tests:
- New in `tests/unit/`: `test_rundir_resolve.py`, `test_store_config.py`,
  `test_rundir_store.py`, `test_store_rules.py`, `test_cmd_store_gc.py`,
  `test_cmd_store_lifecycle.py`, `test_daemon_project_root.py`, and
  `test_cache/test_cache_util_symlink.py`.
- Extended: `test_base_rundir.py`.
- `tests/conftest.py`: autouse `isolate_dfm_config`.

Docs:
- New: `docs/guide/rundir_store.rst`, `docs/reference/site_config.rst`.
- Updated: guide and reference indexes, `guide/running.rst`,
  `guide/runners.rst`, `reference/runner_config.rst`, `reference/cli.rst`,
  `docs/RundirLayout.md`, `docs/ChangeLog.md`.

Working conventions:
- Test command: `packages/python/bin/pytest <paths> > test.log 2>&1`, then
  `tail -30 test.log`. Run the full `tests/unit` suite at the end of each
  phase (log to `test-unit.log`).
- No commits or pushes; the user handles git.
- Each phase leaves the tree green and is shippable by itself.

---

## Survey summary (facts the plan relies on)

- **Rundir computed in 7 places, with 3 different bases:**
  - cwd: `cmds/cmd_run.py:290`, `cmds/cmd_run.py:683` (param-help builder),
    `cmds/cmd_agent.py:100`, `cmds/agent/tui.py:426`,
    `cmds/show/cmd_show_task.py:108`.
  - `pkg.basedir`: `cmds/cmd_graph.py:89`, `cmds/show/cmd_show_task.py:349`.
  - `--clean` runs `rmtree`: `cmd_run.py:300-304` and
    `cmds/agent/context_builder.py:148-153`.
- **`get_rootdir(args)`** (`cmds/util.py:3`) returns `--root`, else
  `$DV_FLOW_ROOT`, else cwd. It does **not** walk up. `.dfm/` is derived from
  it in several places:
  - `daemon.py:60`, `worker_pool_host.py:73`, `daemon_client.py:56,301`
  - `cmds/cmd_daemon.py:56,127,215,252`
  - `runner_config.py:106` (project config)
- **Root flow-file walk-up** is inline in `loadProjPkgDef`
  (`util/util.py:276-302`). The non-elaborating classifier is
  `_classify_flow_file` (`util/util.py:220`).
- **cache_util:** `validate_output_paths` (:222) and
  `convert_output_to_template` (:251).
- **base-rundir:** `task_runner.py` `_try_satisfy_from_base` (:370), restore
  (:407-475, string replace at :473), exec_data `"rundir"` written at :772.
  The option is in `_add_run_opts` (`__main__.py:112`).
- **`task_listener_events.py:122-128`:** `os.path.abspath(rundir)` in the
  `run.start` event. This is fine, because abspath does not resolve symlinks.
- **`DFM_SESSION_RUNDIR`:** set at `task_runner.py:225`; read only by tests.
- **runner_config:**
  - Path helpers `_install_config_path` :80, `_site_config_path` :95
    (`~/.config/dfm/site.yaml`), `_project_config_path` :103.
  - `_load_yaml` :112; `load_runner_config` :232.
  - Called from `cmd_run.py:321` and `cmd_daemon.py:72`.
- **CLI:**
  - `_lazy` is at `__main__.py:39`. `_add_run_opts` (:98) is used only by
    `run`. `--root` is redeclared per command; there is no shared helper.
  - `cache` nested subparser: :543-557, dispatched via `args.cache_func`
    (`cmds/cmd_cache.py:29`).
  - `show` subparsers: :347, plus a hand-written list in `cmds/cmd_show.py`
    (~:40-50).
- **Reusable bits:**
  - `cache_lock.FileLock` (async fcntl).
  - `std/publish.py:136 _atomic_symlink` and its flock context (:177-185).
  - There is no generic atomic-write helper.
- **Entry points:** `pyproject.toml` `[project.entry-points."agent.skills"]`
  (:39). Plugin discovery lives in `ext_rgy.py:187-210`.
- **Tests:**
  - `pytest.ini` sets `testpaths = tests`. `tests/conftest.py` autouse unsets
    `DV_FLOW_CACHE` except for `test_cache*` paths.
  - Templates: `tests/unit/test_base_rundir.py` (`_run_flow` helper),
    `tests/unit/test_runner_config.py`, `tests/unit/test_cmd_run_frontend.py`,
    `tests/unit/test_cache/test_cache_util.py`.
- **Docs:**
  - Sphinx (`docs/index.rst`, with `guide/` and `reference/` toctrees).
  - `docs/RundirLayout.md` (md outline). `docs/ChangeLog.md` (`# Unreleased`
    section, bold-led bullets).
  - `docs/reference/runner_config.rst` (Merge Rules :123, Environment
    Variables :146). `docs/reference/cli.rst` (base-rundir ~:170).
  - `docs/guide/runners.rst:70` mentions `site.yaml`.

---

## Cross-cutting design choices for the implementation

1. **One module, `rundir_store.py`**, owns rundir resolution. Store-entry
   logic lives in `rundir_store_entry.py` (naming, metadata, lock,
   classification) so the `dfm store` commands can import it without CLI
   baggage. Config resolution lives in `store_config.py`. The plugin registry
   lives in `site_config.py`.
2. **`resolve_rundir()` has two modes.**
   - `create=True` is for `run`, `agent`, `context` and the TUI. It may create
     the entry and link, takes the session lock, and updates `last_used`.
   - `create=False` is for `graph`, `show task` and param-help at
     `cmd_run.py:683`. It is pure path computation and never touches disk.
     Display-only commands must not create store entries.
3. **Return value.** It returns a small dataclass `RundirInfo(path, pkg_root,
   mode: local|store|symlink, entry: Optional[str], lock: Optional[...])`.
   `path` is always the logical `<pkg_root>/rundir`. Callers that only want a
   string use `.path`.
4. **Session lock lifetime.** The lock is a sync `fcntl.flock` on an open fd
   held by `RundirInfo`. It is released by `RundirInfo.close()` (also a
   context manager), and the fd is set `O_CLOEXEC` so tool subprocesses do not
   inherit it. Async `cache_lock.FileLock` does not fit, because resolution
   happens before the event loop.
5. **Shared store options.** Add `_add_store_opts(p)` in `__main__.py`
   (`--store DIR`, `--no-store`, `--store-recreate`). Apply it to `run`,
   `agent`, `context` and `store` (and to `_add_run_opts` via run). Because
   `reserved_option_strings()` is derived from the parser, the new run flags
   become reserved automatically. Check them against
   `test_cmd_run_frontend.py:103`.
6. **Package-root finder.** Extract the inline walk-up from `loadProjPkgDef`
   into `find_root_flow_file(start) -> Optional[str]` in `util/util.py`, and
   have `loadProjPkgDef` call it, so there is a single source of truth.
   `find_pkg_root(args)` is `dirname(find_root_flow_file(get_rootdir(args)))`.

---

## Phase 1 — Package-root rundir, symlink safety

Goal: every command uses the logical `<pkg_root>/rundir`. A hand-made symlink
rundir works, including for `--clean`, caching and base-rundir. A dangling
link is handled. No store config exists yet.

### 1.1 Package-root discovery
- [x] `util/util.py`: extract `find_root_flow_file(start_dir)` from
      `loadProjPkgDef` :276-302, keeping the same file-name order and the same
      `_classify_flow_file` fragment skipping. `loadProjPkgDef` calls it.
- [x] `rundir_store.py`: `find_pkg_root(args) -> Optional[str]`, built on
      `get_rootdir(args)` and `find_root_flow_file`.

### 1.2 `resolve_rundir()` (local and symlink modes only)
- [x] `rundir_store.py`: `RundirInfo` dataclass and
      `resolve_rundir(pkg_root, *, create, cwd=None) -> RundirInfo`.
  - [x] `pkg_root is None` falls back to `cwd/rundir` and logs a warning (D7).
  - [x] Implement the §6.1 decision table, minus the store rows. A missing
        link becomes `mkdir`. A real dir is used as is. A symlink to an
        existing dir is used as is (hand-made, §6.2 first bullet). A regular
        file is an error.
  - [x] Dangling-link handling (§6.4) without the store: recreate the target
        if its parent exists, and log the info message. Otherwise raise
        `RundirError` with the guidance text. (`relink` and `unlink` are
        mentioned in the text, but they arrive in phase 6, so word the
        guidance to suit what exists.)
  - [x] Transition note: if `cwd != pkg_root` and `cwd/rundir` exists, print
        a one-time note (§6.0). "One-time" means once per process, since
        there is no persistent state. Use a module-level flag.
- [x] `clean_rundir(path)`: remove the contents of `realpath(path)`, keeping
      `.dfm-rundir.json` and `.dfm-rundir.lock`. Never unlink `path`. Use
      `os.scandir` with `rmtree` per child, and `unlink` for files and
      symlinks.

### 1.3 Route call sites
- [x] `cmds/cmd_run.py:290`: use `resolve_rundir(pkg.basedir, create=True)`.
      This needs `pkg` loaded first; verify the ordering against the
      `loadProjPkgDef` call. Replace :300-304 with `clean_rundir`.
- [x] `cmds/cmd_run.py:683`: `create=False`.
- [x] `cmds/cmd_graph.py:89`: `create=False`.
- [x] `cmds/show/cmd_show_task.py:108,349`: `create=False`, consistent.
- [x] `cmds/cmd_agent.py:100`, `cmds/agent/tui.py:426`: `find_pkg_root`, then
      `create=True`.
- [x] `cmds/agent/context_builder.py:148-153`: `clean_rundir`.
- [x] Hold `RundirInfo` for the session lifetime in `cmd_run` and agent, and
      close it at exit. In phase 1 it holds no lock; this is wiring only.

### 1.4 `.dfm/` follows the package root
- [~] (done differently; see Implementation notes) Add `get_project_root(args)` (in `cmds/util.py`): `find_pkg_root(args)`
      or `get_rootdir(args)`. Use it for:
  - `cmd_run.py:111,144,319`
  - `runner_config` project path (`cmd_run.py:321`, `cmd_daemon.py:72`)
  - `cmd_daemon.py:56,127,215,252`
  - the `project_root` passed into `daemon.py`, `worker_pool_host.py` and
    `daemon_client.py`
- [x] Leave `get_rootdir` callers that need the start dir (`cmd_complete`,
      `show tags/packages/types`, `cmd_validate`) unchanged. Audit each and
      note it here.
- [x] Daemon compatibility: a daemon started under the old `<cwd>/.dfm` is
      not found from the new location. Document this in the ChangeLog
      ("restart daemons after upgrade"). No shim.

### 1.5 Symlink-safety fixes (§7)
- [x] `cache_util.validate_output_paths` (:222) and
      `convert_output_to_template` (:251): accept a basedir under either
      `abspath(rundir)` or `realpath(rundir)`, and compare each against its
      own form (realpath'd basedir against realpath rundir). Factor out a
      `_rel_to_rundir(path, rundir) -> Optional[str]` helper.
- [x] `task_runner.py:473` base-rundir restore: try `replace` with both
      `saved_rundir` and `realpath(saved_rundir)`, using path-prefix matching
      (`startswith(prefix + os.sep)` or equality), not substring `replace`.
- [x] `task_runner.py:225`: `DFM_SESSION_RUNDIR` is the logical path. Assert
      that `self.rundir` is never realpath'd upstream; grep for
      `realpath`/`resolve()` on rundir in `task_runner.py`, `task_node*.py`
      and `std/`.
- [x] `task_listener_events.py:125`: abspath is fine; no change. Record the
      audit result here.
- [x] `cmd_run.py:292-298` (`--base-rundir`): `abspath`, not `realpath`.
      Allow a symlink target.

### 1.6 Tests — `tests/unit/test_rundir_resolve.py` (new)
- [x] `find_root_flow_file`: walks up from a subdir, skips a fragment, and
      returns None when there is no package.
- [x] Run from a subdir and the rundir is `<pkg_root>/rundir`. A stale
      `<subdir>/rundir` triggers the note, printed once.
- [x] No package: falls back to `cwd/rundir` with a warning.
- [x] Hand-made symlink rundir: the run succeeds and outputs land in the
      target.
- [x] `create=False` on a missing rundir creates nothing.
- [x] Dangling link with the parent present: recreated, with the info
      message. With the parent absent: `RundirError` text.
- [x] Regular file at `rundir`: error.
- [x] `clean_rundir` on a symlink: the link survives, contents are gone, and
      `.dfm-rundir.json` and `.dfm-rundir.lock` are preserved.
- [x] Extend `tests/unit/test_cache/test_cache_util.py`:
      `validate_output_paths` and `convert_output_to_template` with a
      symlinked rundir, for logical and realpath'd basedirs.
- [x] Extend `tests/unit/test_base_rundir.py`: the base rundir is a symlink;
      exec_data recorded via the logical path is restored when the realpath
      is supplied, and vice versa. Add a prefix-collision case (`/x/rundir`
      vs `/x/rundir2`).
- [~] (unit-level only; see Implementation notes) Cached-run replay through a symlinked rundir (the cache_util
      regression). Model it on the existing `test_cache` integration tests;
      the file name must contain `test_cache` so `DV_FLOW_CACHE` is kept.
- [x] Daemon/`.dfm` location test: `get_project_root` from a subdir.

### 1.7 Docs
- [x] `docs/ChangeLog.md` `# Unreleased`:
  - **Rundir now lives at the package root**, covering the subdir behaviour
    change, the stale-dir note, `.dfm/` moving, and the daemon restart.
  - Fix: **`--clean`, output caching and `--base-rundir` work with a
    symlinked rundir**.
- [x] `docs/RundirLayout.md`: state the location (package root) and that
      `rundir` may be a symlink.
- [x] `docs/guide/running.rst`: a short "Where the rundir lives" paragraph,
      plus the gitignore advice (use `rundir`, not `rundir/`).

---

## Phase 2 — Config plumbing

Goal: the store root resolves from CLI, env, user, site and install with
provenance. The project file can only opt out. Nothing uses the value yet
except `resolve_rundir`, which only reports it (no entries until phase 3).

### 2.1 Config file locations (shared with runner config)
- [x] `config_paths.py` (new, or extend `runner_config.py`; prefer the new
      module and re-export):
  - `user_config_paths()`: `$DFM_USER_CONFIG`, else
    `$XDG_CONFIG_HOME/dfm/config.yaml` (default `~/.config/dfm`), plus the
    legacy `site.yaml`.
  - `site_config_path()`: `$DFM_SITE_CONFIG`, else `/etc/dfm/config.yaml`.
  - `install_config_path()`: move the existing `_install_config_path`.
  - `project_config_path(pkg_root)`.
- [x] Legacy alias: if `site.yaml` exists, read it. If both `config.yaml` and
      `site.yaml` exist, `config.yaml` wins key-by-key. Log a one-time
      deprecation note (debug level if `config.yaml` also exists, otherwise
      info).
- [x] `runner_config.load_runner_config`: switch to the new helpers. The
      layer order becomes install → **site (`/etc`)** → user → project. This
      adds the real site layer and keeps the runner's project-beats-user
      rule. Keep `_site_config_path` as a deprecated alias returning the
      legacy path, so existing imports and tests keep working.
- [x] Update `tests/unit/test_runner_config.py` for the new layer and alias.

### 2.2 Store config resolution
- [x] `store_config.py`:
  - `StoreDecision(root: Optional[str], create: bool, provenance: str,
    chain: list[tuple[str, str]])`. `root=None` means local.
  - `resolve_store(pkg_root, cli_store, cli_no_store, env=os.environ) ->
    StoreDecision`.
  - Order (§5.3):
    1. CLI
    2. `DFM_STORE`
    3. user
    4. site
    5. install
    6. plugin (stubbed to None until phase 5)
    7. local
  - Project opt-out applies after 3-6 and before the default; CLI and env
    beat it.
  - `chain` records every layer consulted and its answer, for `store info`.
  - In each file, read the `store:` key: `root` (str), `create` (bool,
    default true), and `rules` (parsed, but ignored until phase 5; warn
    "rules not yet supported" — remove the warning in phase 5).
  - Project file: `root: local` or `""` is accepted. Any other `root` or any
    `rules` gives a warning and is ignored.
  - `root` values `""` and `"local"` both mean local.
  - Expand `${VAR}` from the env here. The `${user}`-style facts come in
    phase 5; for now, support `${USER}`/`${HOME}` via env only.
  - Make relative `root` paths in files relative to the file's directory, or
    reject them. **Pick: reject with a warning** (simpler, unambiguous).
- [x] `__main__.py`: `_add_store_opts(p)` (`--store DIR`, `--no-store`,
      `--store-recreate`, mutually exclusive where it applies). Apply it to
      `run` (inside `_add_run_opts`), `agent` and `context`.
- [x] `resolve_rundir` gains a `store: StoreDecision` parameter. In phase 2 a
      configured store on a missing link logs a debug message and still does
      `mkdir`. **Alternative:** land phases 2 and 3 together if the
      intermediate state seems confusing. Decide at phase start.

### 2.3 Tests — `tests/unit/test_store_config.py` (new)
- [x] Precedence matrix (parametrized): each layer set alone, then pairs to
      show the higher layer wins. Check provenance strings: `cli:--store`,
      `env:DFM_STORE`, `user-config:<p>`, `site-config:<p>`,
      `install-config:<p>`, `default:local`.
- [x] `DFM_STORE=""` and `DFM_STORE=local` disable the store, beating a user
      file.
- [x] Project `root: local` beats user, site and install, and loses to CLI
      and env.
- [x] Project `root: /abs` or `rules:` gives a warning and is ignored.
- [x] `--no-store` beats everything.
- [x] `$XDG_CONFIG_HOME` is honoured. `DFM_USER_CONFIG` and `DFM_SITE_CONFIG`
      overrides work.
- [x] Legacy `site.yaml` is read, with the deprecation note. `config.yaml`
      beats `site.yaml`.
- [x] `${VAR}` expansion; a relative root is rejected.
- [x] Parser: the new flags are present and reserved
      (`test_cmd_run_frontend.py`).
- [x] All tests isolate env via `monkeypatch.setenv` /
      `monkeypatch.delenv` and `tmp_path` config dirs. Add a shared fixture
      `isolated_dfm_config` to `tests/conftest.py` (non-autouse). It points
      `DFM_USER_CONFIG`, `DFM_SITE_CONFIG` and `DFM_INSTALL_CONFIG` at
      tmp_path and unsets `DFM_STORE`.

**Global safety:** add an autouse fixture in `tests/conftest.py` that unsets
`DFM_STORE` and points `DFM_USER_CONFIG` and `DFM_SITE_CONFIG` at
non-existent files. Without it, a developer's real store config leaks into
the whole test suite. This is important once phase 3 makes the store live.

### 2.4 Docs
- [x] `docs/reference/runner_config.rst`: update the file-layer table
      (user `config.yaml`, legacy `site.yaml`, new `/etc/dfm/config.yaml`)
      and add `DFM_USER_CONFIG`/`DFM_SITE_CONFIG` to Environment Variables.
- [x] `docs/guide/runners.rst:70`: `site.yaml` becomes `config.yaml`, with a
      note about the legacy alias.
- [x] ChangeLog: **User config moves to `~/.config/dfm/config.yaml`; new
      site config `/etc/dfm/config.yaml`**.

---

## Phase 3 — Store entries, `dfm store info` / `init`

Goal: with a store configured, a fresh project gets a store entry and a
symlink. Copy, move and dangling cases are handled. The session lock is held.

### 3.1 `rundir_store_entry.py`
- [x] `mangle(link) -> str`: replace `/` with `_`. Apply the length rule
      (more than 200 bytes becomes the last 160 bytes plus `__<hash8>`).
      Encode to bytes for the length check.
- [x] `entry_hash(host, uid, link)` is `sha1(f"{host}:{uid}:{link}")[:8]`.
- [x] `choose_entry_name(store_root, link, host, uid)` (§4.1 collision rule).
      Collision means the existing entry's metadata has a different `link`,
      or a different `host` when the link is host-local, or a different
      `uid`. **Define "host-local"** as follows for v1: treat host as part of
      identity only when `meta.host != this host` **and** the link's parent
      is not visible. Simpler alternative: always include host. Decide at
      implementation and record it here.
- [x] `EntryMeta` dataclass and `read_meta(entry)` / `write_meta(entry,
      meta)`. The atomic write uses a tmp file in the same dir, `fsync`, then
      `os.replace`. Add a generic `util/atomic.py:atomic_write_text(path,
      text)` and reuse it.
- [x] `touch_last_used(entry)`: read, update, atomic write. Tolerate
      concurrent writers; last writer wins.
- [x] `EntryLock`: sync `fcntl.flock`, shared or exclusive, optionally
      non-blocking, `O_CLOEXEC`, as a context manager.
- [x] `store_marker`: `read_marker(root)`, `write_marker(root, mode)`,
      `is_store_root(dir)`.
- [x] `gather_project_facts(link, pkg_root, package)`: user (`getpass`), uid,
      host (`socket.gethostname()`, short form), dfm_version, and git facts
      (lazy; phase 5 adds the full `StoreContext`, while phase 3 just
      collects remote and branch with a 2s timeout and tolerates failure).
- [~] (new helper only; publish not changed) `atomic_symlink(target, link)`: reuse or lift
      `std/publish.py:136 _atomic_symlink` into `util/atomic.py`, and make
      publish import it from there.

### 3.2 `resolve_rundir` store paths
- [x] Missing link with a store configured (§6.3):
  1. Root check. With `create` and an existing parent, `makedirs`;
     otherwise `RundirError`.
  2. If the marker is absent, write it (mode `private`).
  3. Choose the name, then `mkdir` (no exist_ok). On `EEXIST`, re-read the
     metadata: if it is ours, use it; otherwise re-choose with the hash
     suffix.
  4. Write the metadata.
  5. Create the link with `atomic_symlink`.
  6. Lock and touch.
- [x] Real-dir link with a store configured: one-time
      `dfm store migrate` hint (D6).
- [x] Symlink to an existing entry (§6.2):
  - [x] Unmanaged target (no metadata, parent not a store): use it as is.
  - [x] `meta.link == L`: lock shared, then touch.
  - [x] **Copied** (`meta.link` exists and realpaths to the same entry):
        warn, create a fresh entry, repoint `L`.
  - [x] **Moved**: rewrite the metadata (link, project_root, host),
        `os.rename` the entry to the new mangled name (on collision, keep the
        old name), repoint `L`. The rename happens under an exclusive
        non-blocking lock; if busy, skip the rename and only rewrite the
        metadata.
- [x] Dangling (§6.4), store-aware: if the parent is a store root, recreate
      it with fresh metadata. `--store-recreate` / `DFM_STORE_RECREATE=1`
      relinks to the *configured* store, even when the old parent is missing.
- [x] Sticky link: if the entry's store differs from the configured store,
      record the mismatch in `RundirInfo` (shown by `store info`); do not
      move.
- [x] Gitignore check is deferred to `migrate` (§7.5). On first link
      creation, if `git check-ignore -q rundir` fails, warn once. This is
      cheap, and only applies when inside a git repo.

### 3.3 `dfm store` command skeleton
- [x] `__main__.py`: a `store` subparser with nested subparsers, following
      the `cache` pattern (:543-557). Dispatch is
      `func=_lazy(".cmds.cmd_store","CmdStore")` and
      `store_func=_lazy(".cmds.store.cmd_<x>", ...)`.
- [x] `cmds/cmd_store.py` dispatcher. `cmds/store/__init__.py`.
- [x] `cmds/store/cmd_info.py`:
  - Prints the resolved decision and the provenance chain.
  - Prints the project link state: local, ok, dangling, copied, moved,
    unmanaged-symlink, store-mismatch, none.
  - Prints the entry path and metadata summary.
  - Supports `--json`.
  - Uses `create=False` semantics: it inspects only, never creates.
- [x] `cmds/store/cmd_init.py`:
  - `init <dir> [--shared|--group]` does `makedirs`, writes the marker, and
    chmods to 1777 or 2775.
  - It is idempotent and reports an existing marker.

### 3.4 Tests — `tests/unit/test_rundir_store_entry.py`, `tests/unit/test_rundir_store.py`, `tests/unit/test_cmd_store_basic.py`
- [x] `mangle`: the example from the design (`/home/u/p/rundir` →
      `_home_u_p_rundir`) and the length rule. Check the resulting name is
      at most 200 bytes, including multibyte paths.
- [x] Collision `/a_b/rundir` vs `/a/b/rundir` produces the hash suffix.
- [x] Metadata round-trip. The atomic write leaves no tmp file behind when
      replace fails (simulate this with monkeypatch).
- [x] Fresh run with a store: the link is a symlink into the store, and the
      metadata fields are correct (link, project_root, package, user, uid,
      host, store_source, created, last_used).
- [x] A second run updates `last_used` and reuses the entry.
- [x] Concurrent create: two `resolve_rundir` calls racing (threads, or a
      pre-created entry dir) end with exactly one entry.
- [x] Copy (`shutil.copytree(symlinks=True)`): forked into a new entry; the
      original is untouched.
- [x] Move (`os.rename` of the project dir): adopted, entry renamed,
      metadata updated.
- [x] Dangling link with the store root present: recreated. With it absent:
      error text. With `--store-recreate`: relinked to the configured store.
- [x] Store root missing: with its parent present, auto-created with a
      marker. With the parent absent, an error. With `create: false`, an
      error.
- [x] Real local rundir with a store configured: stays local, and the hint
      is printed once.
- [x] Sticky link: change `DFM_STORE`, and the old link is still used;
      `store info` reports the mismatch.
- [x] The session lock is held during a run. A second, exclusive
      non-blocking lock attempt fails while it is held (test this directly on
      `EntryLock` with a held `RundirInfo`).
- [x] `--clean` in store mode keeps the link, metadata and lock file.
- [x] Full `dfm run` round-trip with cache replay in store mode (file name
      contains `test_cache`).
- [x] `--base-rundir` pointing at another project's store entry, through its
      link and through its realpath.
- [x] `store init`: marker contents and modes 1777 and 2775 (check
      `stat.S_IMODE`). Re-init is idempotent.
- [x] `store info --json` structure, for each link state.

### 3.5 Docs
- [x] Start `docs/guide/rundir_store.rst` (or `docs/RundirStore.md`; the
      design says `.md`, but the guide dir is `.rst` — **use
      `docs/guide/rundir_store.rst`** and add it to the `guide/index`
      toctree). Cover: concept, enabling via `DFM_STORE` or the user config,
      `store init`, `store info`, copy and move behaviour, and dangling-link
      recovery.
- [x] ChangeLog: **Rundir store**: `DFM_STORE`, `store:` config,
      `dfm store info|init`.

---

## Phase 4 — `dfm store list` / `gc`

### 4.1 Classification
- [x] `rundir_store_entry.classify(entry, this_host) -> Status`, implementing
      §8.1:
  - `busy` (exclusive non-blocking lock fails) is checked first.
  - `unmanaged`: no metadata.
  - `ok` / `retargeted` / `orphan` / `unknown`, with the visibility test:
    `os.path.isdir(dirname(meta.link))` or `meta.host == this_host`.
- [x] `scan_store(root) -> Iterator[EntryRecord]` skips the marker and lock
      files and non-directories.
- [x] `entry_size(path)`: `os.scandir` walk without following symlinks.
      Parallel via `ThreadPoolExecutor` (8 workers by default), opt-in.

### 4.2 Commands
- [x] `cmds/store/cmd_list.py`:
  - Options: `--store DIR`, `--user U` / `--all-users` (default: current
    user), `--status S` (repeatable), `--size`, `--sort size|age|name`,
    `--json`.
  - Output: a table with name, link, user, host, last used (relative), status
    and size.
  - Without `--store`, it uses the configured store and errors if there is
    none.
- [x] `cmds/store/cmd_gc.py`:
  - Options: `--orphans`, `--older-than DUR` (`30d`, `12h`, `2w`),
    `--include-unknown`, `--user` / `--all-users`, `--dry-run`, `-y`,
    `--force`.
  - The selection logic follows §8.1/§8.2:
    - With no criteria, it means `--orphans`.
    - `--older-than` combined with `--orphans` is an AND.
    - `busy` and `unmanaged` are never removed.
    - Without `--force`, entries whose `last_used` is under 1h old are
      skipped (the NFS fallback).
  - It refuses to run without a `.dfm-store.yaml` marker.
  - It takes `.dfm-store.lock` exclusively for the gc run, then takes each
    entry's lock exclusively and non-blocking just before deleting it, and
    deletes under that lock. Deleting means: rename to `.gc-<name>-<pid>`,
    then `rmtree`. The lock file goes with the directory.
  - It prints the plan (count and size) and asks for confirmation unless
    `-y` or `--dry-run`. It refuses to prompt without a TTY unless `-y`.
  - It reports a summary of entries removed and bytes freed.
  - Deleting another user's entry may fail on a 1777 store. Report the
    error and continue.
- [x] `parse_duration()` helper.

### 4.3 Tests — `tests/unit/test_cmd_store_gc.py`
- [x] Build a synthetic store fixture with each status:
  - ok: a real link.
  - orphan: the link is deleted; same host.
  - retargeted: the link replaced by a dir, or pointing elsewhere.
  - unknown: `meta.host="otherhost"`, link parent absent.
  - busy: a lock held by the test.
  - unmanaged: no metadata.
- [x] `classify` for each status.
- [x] `gc --dry-run` deletes nothing but lists the correct plan.
- [x] `gc -y` removes orphan and retargeted entries only.
      `--include-unknown` adds unknown. busy and unmanaged always survive.
- [x] `--older-than` alone vs with `--orphans`. `last_used` is set via the
      metadata.
- [x] The 1h fallback: a fresh orphan is skipped unless `--force`.
- [x] `--user` filtering (fake uid/user in the metadata). `--all-users`.
- [x] No marker means gc refuses.
- [x] `list --json` fields. `--size` is correct on a small tree. `--sort`.
- [x] A dangling link left by gc'ing an ok entry with `--older-than` is
      recovered on the next run (ties to §6.4).

### 4.4 Docs
- [x] Guide page: "Analysing and cleaning the store" with `list` and `gc`
      examples, the status table and cross-host notes (§8.2). Suggest a cron
      line.
- [x] `docs/reference/cli.rst`: a `dfm store` section listing all
      subcommands and options. Grow it per phase.

---

## Phase 5 — Rules, git context, Python SiteConfig

### 5.1 StoreContext and rules
- [x] `site_config.py`: a frozen `StoreContext` dataclass (§5.4). The lazy
      `git_remote()` and `git_branch()` are cached through a private mutable
      holder, because the dataclass is frozen. `git_org`/`git_repo` parsing
      handles scp-style (`git@host:org/repo.git`), https, and ssh:// URLs.
- [x] Rule matching in `store_config.py`:
  - Supported keys: `path`, `link`, `user`, `host`, `git-remote`,
    `git-branch`, `package`, and `env` (a map).
  - fnmatch only. `**` in the `path` example (§5.1) means fnmatch `*`
    already crosses `/`; document that `*` matches across separators.
  - All keys must match. Unknown keys give a warning and the rule never
    matches.
  - Git facts are queried only if a rule uses a git key.
- [x] Template expansion in `root`: `${user}`, `${host}`, `${package}`,
      `${git_org}`, `${git_repo}`, then env. An unresolved variable makes the
      rule skip with a warning; it is not an error.
- [x] In each file layer, rules come first (first match), then `root`.
      Provenance is `user-rule:<name>`, `site-rule:<name>` and so on.
- [x] Remove the phase-2 "rules not yet supported" warning.

### 5.2 Plugin registry
- [x] `site_config.py`: `SiteConfig` base and `SiteConfigRgy`.
  - Load the entry-point group `dv_flow.mgr.site_config` via
    `importlib.metadata.entry_points(group=...)`. Accept a class or a
    zero-argument factory.
  - Selection: `DFM_SITE_CONFIG_NAME`, then `site-config:` in the user or
    site YAML, then the last one registered.
  - A load failure produces a warning and is skipped.
  - Cache the result per process.
- [x] Wire layer 6 in `resolve_store`. Provenance is
      `site-config:<ClassName>`.
- [x] `pyproject.toml`: document the group with a commented example only.
      The core package does not register a plugin.

### 5.3 `dfm show site-config`
- [x] `cmds/show/cmd_show_site_config.py`: the active plugin and how it was
      selected, all registered plugins, the config files consulted (exists or
      missing), and the store decision chain for the current project.
      Supports `--json`.
- [x] Register it in `__main__.py:347` show subparsers, export it in
      `cmds/show/__init__.py`, and add it to the list in `cmds/cmd_show.py`.
- [x] `store info` reuses the same chain renderer.

### 5.4 Tests — `tests/unit/test_store_rules.py`, `tests/unit/test_site_config.py`
- [x] Each match key individually, and AND across keys.
- [x] git-remote and branch against a real `git init` repo in tmp_path with
      `remote add origin`. A non-git project fails to match git rules but
      does not error.
- [x] Git is not invoked when no rule needs it (monkeypatch subprocess and
      assert it is not called).
- [x] Template expansion, including git_org/git_repo for scp, https and ssh
      URLs. An unresolved variable skips the rule.
- [x] User rules beat a site `root`. Site rules beat a site `root`.
      First match wins.
- [x] Plugin: register a fake via a monkeypatched `entry_points` (inject a
      fake `EntryPoint`). Check `DFM_SITE_CONFIG_NAME` selection, YAML
      `site-config:` selection, and last-registered default. A broken plugin
      gives a warning. Returning None defers to local; returning `"local"`
      means local.
- [x] The plugin is consulted only after all YAML layers say nothing.
- [x] `show site-config --json` output.

### 5.5 Docs
- [x] `docs/reference/site_config.rst` (new, added to the reference
      toctree):
  - YAML `store:` schema, rule keys, templates and precedence.
  - Writing a `SiteConfig` plugin, with a worked example: an LDAP-group-based
    choice, and a `pyproject.toml` entry-point snippet.
  - Env vars: `DFM_STORE`, `DFM_STORE_RECREATE`, `DFM_USER_CONFIG`,
    `DFM_SITE_CONFIG`, `DFM_SITE_CONFIG_NAME`, `DFM_INSTALL_CONFIG`.
- [x] Guide page: a "Site administrators" section linking to the reference.
- [x] ChangeLog: **Site config: store rules and `dv_flow.mgr.site_config`
      plugins; `dfm show site-config`**.

---

## Phase 6 — `migrate` / `unlink` / `relink`, final docs

### 6.1 Commands (`cmds/store/cmd_migrate.py`, `cmd_unlink.py`, `cmd_relink.py`)
- [x] `migrate`:
  - It requires a real-dir `L` and a configured store.
  - It takes an exclusive lock on a temporary project-side lock
    (`<pkg_root>/.dfm/rundir.lock`), so it is not run during a session.
  - Steps:
    1. Create the entry (metadata included).
    2. Move the contents: `os.rename` per child if on the same filesystem
       (`st_dev`), otherwise `shutil.copytree` and verify.
    3. Rename `L` to `L.migrating.<pid>`.
    4. `atomic_symlink`.
    5. Remove the old dir.
  - On failure, it rolls back by renaming back.
  - It warns if `git check-ignore -q rundir` fails, and suggests fixing
    `rundir/` → `rundir`.
  - `--dry-run`.
- [x] `unlink [--local] [--keep]`:
  - It removes the link.
  - With `--local`, it moves the contents back: same-fs rename or copy, then
    a real dir. It drops `.dfm-rundir.json` and `.dfm-rundir.lock` from the
    local copy.
  - The entry is removed unless `--keep`.
  - Dangling link with `--local`: create an empty local dir.
- [x] `relink [--store DIR]`:
  - It moves the entry to the target store (configured, or `--store`).
  - If dangling, it creates a fresh entry there.
  - Same-fs uses rename; otherwise copy, then remove.
  - It updates `store_source` in the metadata and atomically repoints `L`.
- [x] Wire `--store-recreate` (phase 3) to reuse the `relink` internals.
- [x] Update the §6.4 dangling-link error text to name the now-real commands.
- [x] All three take the entry lock exclusively and refuse if it is busy.

### 6.2 Tests — `tests/unit/test_cmd_store_lifecycle.py`
- [x] migrate (same fs): contents preserved, the link is created, metadata
      is written, and a subsequent run is a cache/incremental hit (outputs
      still valid, via logical paths).
- [x] migrate across filesystems: simulate by monkeypatching the `st_dev`
      check to force the copy path.
- [x] migrate rollback on an injected failure: `L` is restored.
- [x] migrate gitignore warning (git repo with `rundir/` in .gitignore).
- [x] unlink `--local`: contents are back, metadata is stripped, the entry
      is removed. `--keep` leaves the entry, which then classifies as
      `retargeted`.
- [x] relink to a second store: the entry moved, the link is repointed and
      `store_source` is updated. relink of a dangling link creates a fresh
      entry.
- [x] Busy entry: all three refuse.

### 6.3 Docs (final)
- [x] Complete `docs/guide/rundir_store.rst`: migrate, unlink and relink
      workflows, plus a troubleshooting section (dangling link, unmounted
      store, NFS flock caveat, the gitignore pitfall).
- [x] `docs/RundirLayout.md`: the store entry layout (`.dfm-rundir.json`,
      `.dfm-rundir.lock`) and the store root marker.
- [x] `docs/reference/cli.rst`: complete the `dfm store` section. Document
      `--store`, `--no-store` and `--store-recreate` on `run`. Add a
      cross-reference from the `--base-rundir` section.
- [x] Skills and agent docs: grep `src/dv_flow/mgr/skills/` and `docs/ai/`
      for "rundir" and update location statements (package root, may be a
      symlink).
- [x] ChangeLog: **`dfm store migrate|unlink|relink`**.
- [x] Update the design doc status to "Implemented". Note any deviations in
      §10.

---

## Phase 7 — Statistics and cleanup reporting (design §8.3)

Requested 2026-11-05: actionable stats (age, last access, size, biggest
projects), cleanup facilities (a list of projects to clean up), Rich output
for humans and JSON for agents.

- [x] `rundir_store_entry.py`:
  - `EntryMeta.sessions` (incremented by `touch_meta`; a new entry starts
    at 1).
  - `EntryStats` and `measure()`: allocated and apparent bytes, counting
    hard links once; files, dirs, newest mtime, and the largest top-level
    dirs.
  - Size cache `.dfm-rundir-stats.json` (`read_stats`/`write_stats`, added
    to `KEEP_FILES`). `stats_stale()` is true when the entry was used after
    it was measured.
  - `EntryRecord.to_dict()` is the agent-facing per-entry schema.
- [x] `rundir_store_ops.py`:
  - Size modes `none|cached|measure|refresh` (parallel walks).
  - `EntryFilter` gains `older_than`, `larger_than`, `package` and `host`.
  - `parse_size`; `fs_usage` (statvfs); `aggregate()` (by status, last-use
    bucket, user, host and project, plus largest and reclaimable).
  - `find_candidates()` (tiers safe/review, kinds
    orphan/retargeted/unknown/stale).
  - `plan_gc` gains explicit `selection`, `reclaim` and `target_free`
    (dead entries first, then least recently used).
  - `read_selection`, `resolve_selection`.
- [x] `cmds/store/render.py`:
  - Rich tables with colour-coded status/tier and eighth-block bars.
  - A stacked filesystem bar, and a "Suggested actions" panel.
  - Detail cards for `list --long`; a compact what/size/why table.
  - `json_doc()` wrapper (`schema`, `kind`, `generated`).
- [x] Commands:
  - `stats` and `candidates` (new).
  - `list`: sort, limit, filters, `--long`, `--format`.
  - `gc`: `ENTRY...`, `--from`, `--reclaim`, `--target-free`,
    `--larger-than`, `--package`, `--host`.
  - `info --size`.
- [x] Tests: `tests/unit/test_cmd_store_stats.py` (27 tests).
- [x] Docs:
  - `docs/guide/rundir_store.rst`: the "Analysing and cleaning the store"
    section is rewritten (stats, list, candidates, gc, scripts/agents).
  - `docs/reference/cli.rst` store section; ChangeLog.

Notes:
- `stats`, `candidates` and `gc` measure missing or stale sizes by default
  (`--no-measure` to use only the cache). `list` uses the cache by default
  (`--size` to measure).
- The size cache is best-effort: entries owned by another user are measured
  but not cached.
- A "modified" time comes from the walk. "Last used" is the start of the
  last dfm session, which is cheap and always available.
- `--reclaim` / `--target-free` alone choose from all entries (including
  live ones), LRU-first. The plan shows exactly which entries, and
  `--dry-run` previews it.
- Ideas not implemented:
  - Pruning *inside* an entry (old `out/NNNN` run directories, per-task
    dirs).
  - Per-store quotas or alerts.
  - Recording size at the end of each run (it would cost a walk per run).

## Risks and open implementation decisions

Record each resolution in this section.

- **Phase 2/3 split.** A config that resolves but has no effect could
  confuse users. Possibly ship 2 and 3 together; decide at the start of
  phase 2.
- **Collision identity: host included?** See §3.1. Decide in phase 3.
- **`.dfm/` move breaks running daemons.** Accepted; ChangeLog note.
- **Test-env leakage** of a developer's real `DFM_STORE` or user config.
  Mitigated by the autouse conftest fixture (phase 2).
- **NFS flock.** Mitigated by the `last_used` 1h fallback; documented.
- **Windows.** `fcntl` and symlinks. dfm is Linux-first (`cache_lock`
  already uses fcntl). Guard the import and disable the store on non-POSIX
  with a warning.
- **`cmd_run.py` ordering.** The rundir is computed at :290, before or after
  the package load. If it comes before, restructure so the package loads
  first. Check this at phase 1 start.

## Implementation notes (deviations from the task lists)

- **Phases 2 and 3 shipped together**, so a configured store is never
  inert.
- **Collision identity includes host:** `(link, uid, host)`. When a link is
  created and an entry of the same name exists for another host or user, the
  hashed name is used. Re-using our own orphaned entry (same link, uid and
  host) keeps its contents. A session updates `meta.host` to the last host
  that used it, so NFS projects used from several hosts stay `ok`.
- **Project opt-out precedence** is implemented as CLI > env > project
  opt-out > user > site > install > plugin > local. This is equivalent to
  design §5.3.
- **Plugin provenance** is `site-plugin:<entry-point name>`, not
  `site-config:<Class>`, to avoid clashing with `site-config:<path>` for the
  site file.
- **Liveness is conservative (§8.1):** "visible" means `dirname(meta.link)`
  (the project root) exists, or `meta.host` is this host. A project deleted
  on *another* host is `unknown`, not `orphan`; use `--include-unknown`.
- **Moved project:** the rename to the new mangled name is skipped (metadata
  is still rewritten) if the entry is busy or the name is taken.
- **migrate** takes the entry's exclusive lock, not a project-side lock.
  Local-mode sessions take no lock, so a project lock would not protect
  anything.
- **`std/publish.py:_atomic_symlink` was not lifted.** The new
  `util/atomic.py` is used only by the store code, to avoid churn in
  publish.
- **`context`** does not get the store options; it does not use the
  rundir.
- **`.dfm/` move:** there is no `get_project_root` helper. `cmd_run` uses
  `pkg.basedir`, and `cmd_daemon._get_project_root` uses `find_pkg_root`
  with a fallback to `--root`/cwd. Other `get_rootdir` callers pass it to
  `loadProjPkgDef` as a start directory, so they need no change.
- **Cached-run replay (§1.6):** covered by
  `test_cache/test_cache_util_symlink.py` (the functions that regressed)
  plus up-to-date re-runs through a store link in `test_rundir_store.py`.
  There is no full `DV_FLOW_CACHE` CLI replay test.
- **One-time notes** (stale subdir rundir, migrate hint, gitignore) print
  once per process to stderr. There is no persistent "already told you"
  state.
- **Agent TUI** re-resolves with `lock=False`, because the agent session
  already holds the lock.

## Log

Append one dated line per completed step or decision.

- 2026-11-05: Plan written from the approved design and a code survey.
- 2026-11-05: Phases 1-6 implemented, tested and documented. Full unit,
  integration and system suites green. Not committed.
- 2026-11-05: Phase 7 (stats, candidates, richer list/gc/info, Rich output,
  JSON schema) implemented. Unit suite: 2213 passed. Not committed.
