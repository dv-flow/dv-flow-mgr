# Rundir Store — Design

Status: **Implemented** (2026-11-05). Review decisions are recorded in §10.
Implementation deviations are listed in RUNDIR_STORE_PLAN.md ("Implementation
notes").

## 1. Goal

Today `dfm` puts its rundir at `$(cwd)/rundir`. We want an optional **rundir
store**: a shared root directory (for example `/scratch/storage`) that holds the
rundir contents for many projects. Each project's `rundir` becomes a symlink
into that store:

```
/home/mballance/projects/myproj/rundir  ->  /scratch/storage/_home_mballance_projects_myproj_rundir
```

Requirements:

1. Configure the store location from an env var, from the user config, and at
   the site level. Site-level selection can depend on project facts: user,
   host, git remote URL, path, and so on.
2. Each store entry carries metadata about the project that refers to it, so
   we can detect entries whose project no longer exists.
3. Tools to analyse and clean the store.
4. `dfm` handles a local `rundir` symlink whose target does not exist.

5. The rundir lives in the **package root**, the directory of the root
   `flow.yaml`, not in the cwd. This applies whether the rundir is local or
   in the store.

Non-goals for now: quotas, and remote or object storage.

## 2. Current state (survey)

| Area | Finding | Location |
|---|---|---|
| Rundir path | Hard-coded `os.path.join(os.getcwd(), "rundir")` in 5 places, and `pkg.basedir/rundir` in 2 others. These disagree. | `cmds/cmd_run.py:290,683`, `cmds/cmd_agent.py:100`, `cmds/agent/tui.py:426`, `cmds/show/cmd_show_task.py:108` (cwd); `cmds/cmd_graph.py:89`, `cmds/show/cmd_show_task.py:349` (basedir) |
| `--clean` | `shutil.rmtree(rundir)`. This raises `OSError` if rundir is a symlink. | `cmd_run.py:303`, `cmds/agent/context_builder.py:150` |
| Output caching | Compares `Path(rundir).resolve()` with output paths that are not resolved. A symlinked rundir quietly makes every task uncacheable. | `cache_util.py:232,261` |
| Persisted paths | `exec_data`, mementos and FileSet basedirs store absolute paths. `--base-rundir` restore does a string `replace()`. | `task_runner.py:465-474` |
| Rundir contents | `cache/mementos.json`, `log/`, `bin/` (shims), `out/NNNN` + `out/latest` (relative link), per-task dirs | `task_runner.py:207`, `out.py`, `run_id.py`, `std/publish.py` |
| Config layers | install `<prefix>/etc/dfm/config.yaml` (or `DFM_INSTALL_CONFIG`), then "site" `~/.config/dfm/site.yaml` (which is really a *user* file), then project `.dfm/config.yaml`, then env, then CLI. Only the `runner:` key exists today. | `runner_config.py:80-300` |
| Site plugin | None. dfm has no Python site-config hook. | — |
| Git info | Not collected anywhere at project level. | — |

**Reference: ivpm's mechanism** (`~/projects/fvutils/ivpm`)
- A Python `SiteConfig` subclass is registered via the entry-point group
  `ivpm.site_config`. Exactly one is active, chosen by `IVPM_SITE_CONFIG_NAME`,
  then a `site-config:` key in the YAML files, then the last one registered.
- Hook: `get_cache_provider(context)`. The context is frozen (root name,
  version, dirs). The hook looks up user, host and git itself.
- YAML files: user `$XDG_CONFIG_HOME/ivpm/config.yaml` (`IVPM_USER_CONFIG`) and
  site `/etc/ivpm/config.yaml` (`IVPM_SITE_CONFIG`). Most keys are
  first-file-wins (user before site). Rule lists are concatenated, user first.
- Resolution order: CLI, then env, then user file, then site file, then the
  Python SiteConfig default. Provenance strings (`env:X`, `user-config:<p>`, …)
  are reported by `ivpm show site-config`.
- Declarative match rules (fnmatch, first match wins) exist only for git-auth
  and URL mapping, not for caching.

This design deliberately mirrors ivpm, so that one mental model covers both
tools.

## 3. Concepts and terminology

- **Store root**: a directory that holds store entries. It is marked by
  `<root>/.dfm-store.yaml`.
- **Entry**: one subdirectory of the store root. It *is* a rundir, with the
  usual contents plus a metadata file and a lock file.
- **Package root**: `pkg.basedir` of the root package. This is the directory
  of the `flow.yaml`/`flow.dv` that `loadProjPkgDef` finds by walking up from
  `--root`, `DV_FLOW_ROOT` or the cwd.
- **Link**: the project-side path, `<pkg_root>/rundir`. It is either a real
  directory (local mode) or a symlink to an entry (store mode).
- **Logical rundir**: the link path. dfm uses this path everywhere (see §7),
  never the resolved target.

## 4. On-disk layout

```
$STORE/
  .dfm-store.yaml            # marker: {version: 1, created: ..., mode: shared|private}
  .dfm-store.lock            # flock target used by gc
  _home_mballance_projects_myproj_rundir/
    .dfm-rundir.json         # entry metadata (below)
    .dfm-rundir.lock         # shared flock held while a dfm session uses the entry
    cache/  log/  bin/  out/  <task dirs>...
```

### 4.1 Entry naming

- `name = mangle(abspath(link))`. Mangling replaces `/` with `_`; for
  example, `/home/u/p/rundir` becomes `_home_u_p_rundir`. The name is readable
  and matches the requested example.
- **Collisions.** `/a_b/rundir` and `/a/b/rundir` mangle to the same name. So
  do the same local path on two hosts, such as `/tmp/x` on two farm machines.
  If an entry with that name exists and its metadata has a different
  `(link, host-if-local, uid)`, dfm uses `name + "__" + sha1(host:uid:link)[:8]`
  instead.
- **Length.** If the name exceeds 200 bytes, keep the trailing 160 bytes and
  append `__<hash8>`.
- The name is cosmetic. Identity always comes from the metadata.

### 4.2 Entry metadata (`.dfm-rundir.json`)

```json
{
  "schema": 1,
  "link": "/home/mballance/projects/myproj/rundir",
  "project_root": "/home/mballance/projects/myproj",
  "package": "myproj",
  "user": "mballance", "uid": 1000,
  "host": "build07",
  "git": {"remote": "git@github.com:acme/myproj.git", "branch": "main"},
  "store_source": "site-rule:acme-farm",
  "dfm_version": "1.x.y",
  "created": "2026-11-05T10:00:00Z",
  "last_used": "2026-11-05T12:34:00Z"
}
```

- dfm writes the file atomically (tmp file, then rename) when it creates the
  entry, and updates `last_used` at the start of each session.
- `host` matters for the liveness check (§8.2). It tells us whether the link
  path *should* be visible from the host doing the analysis.

### 4.3 Store root marker

`dfm store gc` refuses to operate on a directory that has no
`.dfm-store.yaml`. This guards against `DFM_STORE=$HOME` accidents.

`dfm store init <dir> [--shared]` creates the marker and sets permissions:
- `--shared` uses `1777` (sticky, like `/tmp`), so users can create entries but
  cannot delete each other's.
- `--group` uses `2775`.

## 5. Configuration

### 5.1 Settings

A new top-level `store:` section is added to the existing config layers. It
is named after the `dfm store` command and the `DFM_STORE` env var.

```yaml
store:
  root: /scratch/${USER}/dfm-store    # "" or "local" = no store (plain <pkg_root>/rundir)
  create: true                        # may dfm auto-create the store root? (§6.3)
  rules:                              # first match wins; evaluated before `root`
    - name: acme-farm
      match:
        git-remote: "*github.com[:/]acme/*"
        host: "farm-*"
      root: /proj/acme/scratch/${user}/dfm
    - name: sandboxes-local
      match:
        path: "/home/*/sandbox/**"
      root: local
```

**Match keys.** All keys use fnmatch. All keys in a rule must match.
- `path`: project root
- `link`
- `user`
- `host`
- `git-remote`
- `git-branch`
- `package`
- `env`: a map of env var name to glob

**Template variables in `root`.**
- `${user}`, `${host}`, `${package}`
- `${git_org}`, `${git_repo}`: parsed from the remote
- `${ENV_VAR}` falls back to the environment.

Git facts are gathered **lazily**, only if a rule or hook asks for them. They
come from `git -C <root> config --get remote.origin.url` and
`rev-parse --abbrev-ref HEAD`, each with a short timeout. Projects that are not
git repos or have no remote simply fail to match.

### 5.2 Files and env vars

These follow ivpm's layout. The existing misnamed `~/.config/dfm/site.yaml`
is cleaned up as part of this.

| Layer | Path | Override env |
|---|---|---|
| CLI | `--store DIR`, `--no-store` | — |
| Env | — | `DFM_STORE` (empty or `local` disables the store) |
| Project | `<pkg_root>/.dfm/config.yaml`: may only opt out (`root: local`), see §5.3 | — |
| User | `$XDG_CONFIG_HOME/dfm/config.yaml` (default `~/.config/dfm/config.yaml`); `site.yaml` is still read as a legacy alias, with a deprecation note | `DFM_USER_CONFIG` |
| Site | `/etc/dfm/config.yaml` | `DFM_SITE_CONFIG` |
| Install | `<sys.prefix>/etc/dfm/config.yaml` | `DFM_INSTALL_CONFIG` (existing) |
| Python site hook | `SiteConfig.get_store(ctx)` | `DFM_SITE_CONFIG_NAME` selects the plugin |

### 5.3 Resolution order

The first layer that yields a decision wins. Within a file layer, that file's
`rules` are evaluated before its plain `root` key.

1. CLI
2. `DFM_STORE`
3. User file
4. Site file
5. Install file
6. Python `SiteConfig.get_store(ctx)`
7. Nothing set: local `<pkg_root>/rundir` (today's behaviour, new location)

**The project file is not a source of store locations.** Where the store lives
is a user, machine and site concern, and a checked-in project cannot know it.
- A project's `.dfm/config.yaml` may set only `store: {root: local}`. This is
  for projects that must keep a local rundir, for example because a tool needs
  the rundir on the same filesystem as the sources.
- Any other `root` or `rules` value in a project file produces a warning and
  is ignored.
- The project opt-out is applied after layers 3-6 but loses to the CLI and
  `DFM_STORE`, so a user can still force a store explicitly.

This intentionally differs from the runner-config layering, where the project
file beats the user file.

**Python hook last.** This matches ivpm. YAML at user or site level can pin or
override whatever the plugin chooses.

Every decision carries a **provenance** string, such as `env:DFM_STORE`,
`user-config:~/.config/dfm/config.yaml`, `site-rule:acme-farm` or
`site-config:AcmeSiteConfig`. It is shown by `dfm store info` and recorded in
the entry metadata.

### 5.4 Python site-config plugin

`dv_flow.mgr.site_config` introduces a `SiteConfig` base class and a registry.
It is independent of ivpm: no import of, and no dependency on, ivpm's config or
plugins. The shape is taken from ivpm's `SiteConfigRgy`:

- Entry-point group `dv_flow.mgr.site_config`. The target is a subclass or a
  zero-argument factory.
- Active selection: `DFM_SITE_CONFIG_NAME`, then `site-config:` in user or site
  YAML, then the last one registered.

```python
@dataclass(frozen=True)
class StoreContext:
    link: str; project_root: str; package: Optional[str]
    user: str; uid: int; host: str
    def git_remote(self) -> Optional[str]: ...   # lazy, cached
    def git_branch(self) -> Optional[str]: ...

class SiteConfig:
    def get_store(self, ctx: StoreContext) -> Optional[str]:
        """Return a store root path, "" / "local" for no store, or None to defer."""
        return None
```

The plugin gives sites full programmatic control: lookups against an LDAP
group, disk-quota checks, and so on. It is also the natural future home for
selecting `DV_FLOW_CACHE` providers, which today are env-var only.

## 6. Runtime behaviour: `resolve_rundir()`

A new module, `rundir_store.py`, provides `resolve_rundir(args, ...) -> str`.
**All** current call sites (§2) use it. This also fixes the cwd vs
`pkg.basedir` inconsistency: everything uses the **package root**.

### 6.0 Locating the package root

- Commands that already load the root package (`run`, `graph`, `show`) use
  `pkg.basedir`.
- Commands that do not (`agent`, the TUI) call a lightweight
  `find_pkg_root(args)`. It uses the same walk-up as `loadProjPkgDef` but does
  not elaborate the package.
- If no root package is found, dfm falls back to `cwd/rundir` and warns.
  `dfm store` subcommands that need a project error instead.
- **Transition.** Running from a subdirectory used to create `<subdir>/rundir`.
  If `cwd != pkg_root` and `cwd/rundir` exists, dfm prints a one-time note that
  it is no longer used and can be deleted. It does not auto-delete it.
- Related: the daemon and worker state directory `.dfm/` is currently placed
  under `get_rootdir(args)`, the start directory. It should also move to the
  package root, so that `.dfm/config.yaml` and the rundir agree.

### 6.1 Decision table

Let `L = <pkg_root>/rundir`.

| State of `L` | Action |
|---|---|
| Does not exist; no store configured | `mkdir L` (today's behaviour). |
| Does not exist; store configured | Create the entry (§6.3), then create the link. The link is created atomically: symlink to `L.tmp.<pid>`, then `os.replace`. |
| Real directory | Use it (local mode). If a store is configured, print a one-time hint: `dfm store migrate`. Never migrate automatically. |
| Symlink, target exists | Validate the entry (§6.2) and use it. |
| Symlink, target missing (**dangling**) | See §6.4. |
| Something else, such as a regular file | Error. |

An existing link is **sticky**. If the configured store changes, dfm keeps
using the existing link and `dfm store info` reports the mismatch.
`dfm store relink` moves the entry.

### 6.2 Entry validation (link exists and resolves)

- **Target is not in a store.** If the target has no `.dfm-rundir.json` and its
  parent has no `.dfm-store.yaml`, it is a hand-made symlink. Use it as is and
  write no metadata.
- **`meta.link == L`.** Update `last_used` and take the shared session lock.
- **`meta.link != L`.** The project was copied or moved:
  - **Copied.** `meta.link` still exists and resolves to the same entry. This
    happens after `cp -a proj proj2`. Both projects would share one rundir,
    which is unsafe. dfm warns, creates a fresh entry for `L` and repoints `L`.
    The new rundir starts empty, as with `--clean`.
  - **Moved.** `meta.link` no longer refers to this entry. dfm adopts the
    entry: it rewrites the metadata, renames the entry to the new mangled name
    and repoints `L`.

### 6.3 Entry creation

1. Resolve the store root from config.
2. If the root is missing:
   - With `create: true` (the default), create it only if its *parent*
     exists. This is a cheap guard against unmounted mount points.
   - Otherwise, error.
   - Write the marker if one is absent.
3. Pick a name (§4.1). Create the entry with `mkdir`, never `exist_ok`, so a
   race between two dfm processes is detected; on `EEXIST`, re-check the
   metadata. Write the metadata.
4. Create the link.

### 6.4 Dangling link

This happens when an entry was gc'd, or the store was wiped, unmounted or
moved.

- **The target's parent exists.** It is the store root, or some other existing
  directory. Recreate the target directory. If it is in a store, write
  metadata. Log `info: rundir entry <T> was missing; recreated (previous
  results are gone)`. This is equivalent to a `--clean`.
- **The target's parent does not exist.** The store is probably unmounted or
  has moved. **Error**, with guidance:

  ```
  rundir -> /scratch/storage/_home_..._rundir, but /scratch/storage does not exist.
    - Mount the store, or
    - dfm store relink            (re-create in the currently configured store), or
    - dfm store unlink --local    (replace link with a local rundir)
  ```

  dfm never silently falls back to a local directory. That would hide results
  and fill home directories.
- Option `--store-recreate` (and env `DFM_STORE_RECREATE=1`) forces relink
  to the currently configured store without asking, for CI.

### 6.5 Session lock

While a dfm session runs, it holds a shared `flock` on
`<entry>/.dfm-rundir.lock`. `dfm store gc` takes an exclusive non-blocking lock
and skips any entry that is busy.

Caveat: `flock` on NFS is unreliable on some setups. As a fallback, gc also
skips entries whose `last_used` is under 1 hour old, unless `--force`.

## 7. Symlink safety inside dfm

These changes are required regardless of the store. They also make
hand-made rundir symlinks work.

1. **Logical path everywhere.** dfm passes `L` (not `realpath(L)`) as
   `self.rundir`, in `DFM_SESSION_RUNDIR`, in `exec_data` and in mementos.
   - Payoff: `migrate`, `relink` and store moves do not invalidate persisted
     paths, because they all still go through `L`.
2. **`cache_util.validate_output_paths` and the `${{ rundir }}` templating.**
   Resolve *both* sides before `relative_to`, or compare against both the
   logical and the resolved prefix. Tools may report realpath'd outputs, so
   accept either.
3. **`--clean`** (`cmd_run.py:303`, `context_builder.py:150`). Replace
   `rmtree(rundir)` with `clean_rundir(L)`. It removes the *contents* of the
   resolved directory, keeping `.dfm-rundir.json` and `.dfm-rundir.lock`. It
   never removes the link itself.
4. **Audit.** Check the remaining `realpath`, `resolve` and `abspath` uses
   along rundir paths: `task_listener_events.py:125` and `--base-rundir`
   string replace (`task_runner.py:465`). For `--base-rundir`, apply the
   `replace` for both the logical and the resolved form of the saved rundir.
5. **Git.** `.gitignore` entries written as `rundir/` do **not** match a
   symlink. Document `rundir` (no trailing slash), and have
   `dfm store migrate` warn if `git check-ignore rundir` fails.

## 8. `dfm store` command

The command lives in `cmds/cmd_store.py` and `cmds/store/cmd_*.py`, using the
existing `cache` subparser pattern (`__main__.py:543-557`).

| Subcommand | Purpose |
|---|---|
| `info` | Shows the resolved store, its provenance chain (every layer consulted and what it said) and the current project's link state (local, ok, dangling, copied, moved, store mismatch). |
| `init <dir> [--shared\|--group]` | Creates the store root marker and permissions. |
| `list [--store DIR] [--user U\|--all-users] [--status S] [--size] [--json] [--sort size\|age]` | Lists entries with: name, link, user, host, last used, status and size. Computing size is opt-in and parallel, because `du` on NFS is slow. |
| `gc [--orphans] [--older-than 30d] [--include-unknown] [--user U\|--all-users] [--dry-run] [-y]` | Deletes entries. With no criteria it means `--orphans`. Prints a plan and asks for confirmation unless `-y`. Defaults to the current user's entries only. |
| `migrate` | Turns local `<pkg_root>/rundir` into a store entry and a symlink: copy (or `rename` on the same filesystem), then swap. |
| `unlink [--local]` | Removes the link. With `--local`, it moves the contents back into a real `<pkg_root>/rundir`. The entry is removed, or left for gc with `--keep`. |
| `relink [--store DIR]` | Moves the current entry to another store, or recreates it there if dangling. |

### 8.1 Entry status classification (used by `list` and `gc`)

| Status | Condition | Removed by `gc --orphans`? |
|---|---|---|
| `ok` | `meta.link` exists, is a symlink and resolves to this entry. | no |
| `orphan` | `meta.link` does not exist, and either `meta.host` is this host or the link's parent directory is visible from here (so the path is checkable). | yes |
| `retargeted` | `meta.link` exists but is a real directory or points elsewhere. | yes |
| `unknown` | `meta.link` is not visible from this host and `meta.host` differs, for example a host-local path on another machine. | only with `--include-unknown` |
| `busy` | The lock is held. | never |
| `unmanaged` | The entry has no `.dfm-rundir.json`. | never (manual) |

`--older-than` works on `last_used`. When combined with `--orphans`, both
conditions must hold (AND). On its own, it selects every entry older than the
age, which is intended for stale but still-linked projects. Removing a linked
entry leaves a dangling link, which §6.4 recovers from.

### 8.2 Liveness across hosts

The checks rely on the link path being visible from the host that runs `gc`.
Home and project dirs are usually NFS. `meta.host` together with the
"is the parent visible?" test separates *project deleted* (orphan) from
*not mounted here* (unknown). Sites with host-local project dirs should run
`gc` per host, or accept `unknown` entries until `--include-unknown`.

## 8.3 Statistics and cleanup reporting (added 2026-11-05)

Who asks what:
- A **user** asks: how much space am I using, which projects are the
  biggest, what is safe to delete, how do I get N GB back?
- A **store admin** asks: who is using the space, how full is the
  filesystem, and how much is dead?
- An **agent** asks the same questions, but needs stable JSON (raw bytes,
  ISO times, ages in seconds), and a list it can filter and feed back into
  `gc`.

#### Per-entry facts

| Fact | Source | Cost |
|---|---|---|
| `created`, `last_used` (start of the last dfm session), `sessions` (count of sessions) | `.dfm-rundir.json`; dfm increments `sessions` on each touch | free |
| status, user, host, package, git remote/branch, link, project root | metadata plus classification | cheap |
| `disk` (allocated bytes, `st_blocks*512`, hard links counted once), `apparent` (`st_size` sum), `files`, `dirs` | tree walk | expensive on NFS |
| `last_modified` (newest mtime in the tree) | same walk | same |
| `top` (sizes of the largest top-level children, i.e. per-task dirs) | same walk | same |

- **Size cache.** Walk results are cached in `<entry>/.dfm-rundir-stats.json`
  with `measured` (ISO time). They are reused unless `--refresh`, or unless
  the entry was used after it was measured; in that case the size is marked
  stale (`~` in tables, `"stale": true` in JSON). A failure to write the
  cache (another user's entry) is ignored.
- Ages are always reported as both an absolute time and a relative age.

#### Filesystem facts

`os.statvfs(store)` gives total, used and free space for the filesystem the
store is on. Store usage is shown as a share of it.

#### Commands

- `dfm store list`:
  - Columns: status, size, last used, created, sessions, user, host,
    package, link.
  - Filters: `--status`, `--older-than`, `--larger-than`, `--package`,
    `--host`, plus the existing `--user` / `--all-users`.
  - `--sort size|last-used|created|name`, `--limit N`, `--long` (also git
    remote/branch, last modified, files, entry path).
  - Sizes come from the cache by default (`--size` measures missing or stale
    ones; `--refresh` re-measures all).
  - A size bar column shows each entry's share of the listed total.
- `dfm store stats`: a dashboard.
  - A **filesystem** panel, with a bar showing store vs other vs free.
  - **Totals**: entry count, store size, number of users.
  - **By status**: count, size and a bar each.
  - **By last use**: age buckets <1d, 1-7d, 7-30d, 30-90d and >90d, with
    count, size and a bar (a histogram).
  - **Top N largest entries**, with bars.
  - **By user**, with `--all-users`.
  - **By project**: git `org/repo`, else package.
  - **Reclaimable**: safe (orphan/retargeted), review (unknown, stale), and
    the commands to reclaim each.
- `dfm store candidates`: the cleanup list.
  - Ranked by reclaimable size.
  - Each entry has a **tier**:
    - `safe`: orphan or retargeted; the project no longer uses it.
    - `review`: either `unknown` (the project can't be checked from this
      host), or `stale` (the project exists but hasn't used the entry for
      `--stale` days, default 30). Deleting a stale entry discards results;
      the next run starts clean.
  - Each entry also has a human-readable reason.
  - Busy, unmanaged and recently used entries are excluded.
  - Formats: table (default), `--json`, `--format names|links|paths` (one
    per line, for piping).
  - Footer: totals per tier, plus ready-to-run commands.
- `dfm store gc` additions:
  - `--larger-than SIZE` is an AND filter.
  - `--reclaim SIZE` takes the selection in least-recently-used order until
    SIZE has been freed.
  - `--target-free SIZE`: reclaim until the filesystem has SIZE free.
  - `--from FILE|-` gives explicit entries as names, links or entry paths, one
    per line, with `#` comments. This is the output of `candidates --format
    names`, after a human or agent has reviewed it.
  - Explicit entries skip the status criteria but never busy entries. They
    skip recently used entries unless `--force`, and other users' entries
    unless `--all-users`.
  - Dry run and confirmation work as before.
- `dfm store info --size` adds the current project's entry size and its
  largest top-level directories.

#### Presentation

- **Humans** get Rich output:
  - Tables with right-aligned sizes in binary units, and relative ages
    ("3d ago").
  - Colour-coded statuses: ok green, orphan/retargeted red,
    unknown/stale yellow, busy cyan, unmanaged dim.
  - Inline unicode bar charts for share of total, the age histogram and
    filesystem usage.
  - A closing "Suggested actions" panel with exact commands.
- When stdout is not a terminal, Rich drops colour, and the layout stays
  readable in logs.
- **Agents** use `--json`. Every JSON document has a `"schema": 1` field,
  sizes in bytes, ISO-8601 UTC times, and ages in seconds. `--format names`
  gives line-oriented output for shell pipelines.

#### Typical loops

```
dfm store stats                                   # where is the space?
dfm store candidates                              # what can go?
dfm store gc -y                                   # take the safe ones
dfm store candidates --tier review --format names > review.txt   # edit
dfm store gc --from review.txt -y
dfm store gc --target-free 500G --dry-run         # what would it take?
```

## 9. Implementation phases

Each phase is independently useful and testable.

1. **Rundir at the package root, symlink-safe.** Add `resolve_rundir()` and
   `find_pkg_root()`, and route all call sites through them. This moves the
   rundir to `<pkg_root>/rundir` (§6.0) and moves `.dfm/` with it. Make the
   §7 fixes (clean, cache_util, base-rundir) and add dangling-link handling.
   Tests use hand-made symlinks. Add a ChangeLog entry for the location change.
2. **Config plumbing.** Add the `store:` section to the config loader, the
   XDG user path with the `site.yaml` alias, the `DFM_SITE_CONFIG`/`/etc` site
   file, `DFM_STORE`, CLI flags and provenance.
3. **Store entries.** Add naming, metadata, entry creation, atomic linking,
   copy/move detection and the session lock. Add `dfm store info` and `init`.
4. **Analysis and cleanup.** `dfm store list` and `gc`.
5. **Site selection.** Add `rules`, the lazy git context, and the Python
   `SiteConfig` registry and entry point, plus `dfm show site-config`.
6. **Lifecycle tools and docs.** Add `migrate`, `unlink` and `relink`. Add a
   docs page (`docs/RundirStore.md`) and update `docs/RundirLayout.md`.

### 9.1 Tests (pytest, using `tmp_path` as the store)

- Fresh run with a store configured: link created, metadata correct, run
  output cached and replayed (this covers the cache_util regression).
- `--clean` on a symlinked rundir keeps the link and the metadata.
- Dangling link with the store root present: recreated. With the root absent:
  error message. With `--store-recreate`: relinked.
- `cp -a` project: a fork is detected and the new entry is created.
  `mv` project: adopted and renamed.
- Name collision (`/a_b` vs `/a/b`): hash suffix.
- Running `dfm run` from a subdirectory uses `<pkg_root>/rundir`, and the
  stale `<subdir>/rundir` note is printed.
- Precedence matrix across CLI, env, user, site, install and plugin, with
  provenance strings. Project `root: local` opts out but loses to CLI and env.
  A project file that sets an absolute `root` produces a warning and is ignored.
- Rule matching on path, host, user and git-remote, with a fake git repo.
- `gc` classification for each status. `--dry-run` deletes nothing. `busy`
  is skipped.
- `--base-rundir` pointing into a store entry.

## 10. Decisions

### Decided (review 2026-11-05)

- **D1. Naming.** The env var is `DFM_STORE`, matching the `dfm store` command.
  The config section is `store:` (key `root`), the CLI flags are `--store DIR`
  and `--no-store`, and the hook is `SiteConfig.get_store()`.
- **D2. Project config.** Projects generally do not specify a store location.
  The project file may only opt out (`root: local`); see §5.3.
- **D3. ivpm.** dfm's site config is separate from ivpm's and has no dependency
  on it. ivpm's shape (entry-point registry, user and site YAML files,
  provenance, first-match rules) is the inspiration.
- **D4. Location.** The rundir lives in the package root. This is part of
  phase 1, not a separate change.

- **D5. Site enforcement.** No for v1. A site cannot require the store;
  users and projects can always opt out.
- **D6. Auto-migrate.** No. An existing local rundir stays local, and dfm
  prints a one-time `dfm store migrate` hint.
- **D7. No root package.** Fall back to `cwd/rundir` with a warning (§6.0).

No open questions remain.
