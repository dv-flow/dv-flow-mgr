"""Locate (and if needed create) a project's rundir.

The rundir is always ``<pkg_root>/rundir`` -- the *logical* path, which dfm
uses everywhere. It is either a real directory (local mode) or a symlink to
an entry in a rundir store (see rundir_store_entry and store_config).

See RUNDIR_STORE_DESIGN.md §6.
"""
import dataclasses as dc
import logging
import os
import shutil
import sys
from typing import List, Optional

from .rundir_store_entry import (
    EntryLock, EntryMeta, KEEP_FILES, dfm_version, entry_lock, hashed_name,
    is_store_root, link_targets_entry, mangle, now_iso, read_meta, touch_meta,
    write_marker, write_meta)
from .site_config import StoreContext
from .store_config import StoreDecision, resolve_store
from .util.atomic import atomic_symlink

_log = logging.getLogger("RundirStore")

RUNDIR_NAME = "rundir"

_notes_shown = set()


class RundirError(Exception):
    """The rundir cannot be used; the message tells the user what to do."""


def _note_once(key: str, msg: str):
    if key in _notes_shown:
        return
    _notes_shown.add(key)
    print(msg, file=sys.stderr)


@dc.dataclass
class RundirInfo:
    """Result of resolving a rundir.

    ``state`` is one of: ``none`` (does not exist), ``local``, ``ok`` (store
    entry linked to this project), ``unmanaged-symlink``, ``copied``,
    ``moved``, ``dangling``, ``file`` (not a directory).
    """
    path: str
    pkg_root: Optional[str]
    state: str
    entry: Optional[str] = None
    meta: Optional[EntryMeta] = None
    store: Optional[StoreDecision] = None
    mismatch: bool = False
    lock: Optional[EntryLock] = None

    @property
    def is_store(self) -> bool:
        return self.meta is not None

    def close(self):
        if self.lock is not None:
            self.lock.release()
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ---------------------------------------------------------------- package root

def find_pkg_root(args=None) -> Optional[str]:
    """Directory of the root flow file found by walking up from ``--root``,
    ``DV_FLOW_ROOT`` or the cwd. Does not load the package."""
    from .cmds.util import get_rootdir
    from .util.util import find_root_flow_file
    start = get_rootdir(args) if args is not None else os.getcwd()
    if os.path.isfile(start):
        return os.path.dirname(os.path.abspath(start))
    f = find_root_flow_file(start)
    if f is None:
        return None
    return os.path.dirname(os.path.abspath(f))


def rundir_path(pkg_root: Optional[str], cwd: Optional[str] = None) -> str:
    """The logical rundir path; never touches the disk."""
    base = pkg_root if pkg_root else (cwd or os.getcwd())
    return os.path.join(os.path.abspath(base), RUNDIR_NAME)


def _check_location(pkg_root: Optional[str], cwd: str):
    if pkg_root is None:
        _note_once("no-pkg", "Warning: no flow.yaml defining a package was found; "
                   "using %s" % os.path.join(cwd, RUNDIR_NAME))
        return
    pr = os.path.abspath(pkg_root)
    if os.path.abspath(cwd) != pr:
        stale = os.path.join(cwd, RUNDIR_NAME)
        if os.path.isdir(stale) and not os.path.islink(stale) \
                and not os.path.exists(os.path.join(cwd, "flow.yaml")) \
                and not os.path.exists(os.path.join(cwd, "flow.dv")):
            _note_once("stale:" + stale,
                       "Note: %s is no longer used; the rundir is now %s. "
                       "The old directory can be deleted." % (
                           stale, os.path.join(pr, RUNDIR_NAME)))


# ---------------------------------------------------------------- helpers

def _abs_target(link: str) -> str:
    t = os.readlink(link)
    if not os.path.isabs(t):
        t = os.path.join(os.path.dirname(link), t)
    return os.path.normpath(t)


def _same_link(a: str, b: str) -> bool:
    """True if two paths name the same link (e.g. via an aliased parent)."""
    try:
        return os.path.samestat(os.lstat(a), os.lstat(b))
    except OSError:
        return False


def clean_rundir(path: str):
    """Empty a rundir without removing it, its link, or the store metadata
    and lock files."""
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        os.makedirs(real, exist_ok=True)
        return
    with os.scandir(real) as it:
        children = list(it)
    for de in children:
        if de.name in KEEP_FILES:
            continue
        if de.is_dir(follow_symlinks=False):
            shutil.rmtree(de.path)
        else:
            os.unlink(de.path)


def make_context(link: str, pkg_root: str, package: Optional[str]) -> StoreContext:
    return StoreContext(link=link, project_root=pkg_root, package=package)


def _new_meta(ctx: StoreContext, source: str) -> EntryMeta:
    git = {}
    remote = ctx.git_remote()
    if remote is not None:
        git = {"remote": remote, "branch": ctx.git_branch()}
    t = now_iso()
    return EntryMeta(
        link=ctx.link, project_root=ctx.project_root, package=ctx.package,
        user=ctx.user, uid=ctx.uid, host=ctx.host, git=git,
        store_source=source, dfm_version=dfm_version(), created=t, last_used=t,
        sessions=1)


def ensure_store_root(decision: StoreDecision) -> str:
    root = decision.root
    if not os.path.isdir(root):
        if not decision.create:
            raise RundirError(
                "Rundir store %s (from %s) does not exist, and 'store.create' "
                "is false. Create it with 'dfm store init %s', or run with "
                "--no-store." % (root, decision.provenance, root))
        parent = os.path.dirname(root)
        if not os.path.isdir(parent):
            raise RundirError(
                "Rundir store %s (from %s) does not exist, and neither does "
                "its parent %s. Is the filesystem mounted? Create it with "
                "'dfm store init %s', or run with --no-store." % (
                    root, decision.provenance, parent, root))
        try:
            os.makedirs(root, exist_ok=True)
        except OSError as e:
            raise RundirError("Failed to create rundir store %s: %s" % (root, e))
    if not is_store_root(root):
        try:
            write_marker(root)
        except OSError as e:
            raise RundirError("Cannot write store marker in %s: %s" % (root, e))
    return root


def create_entry(decision: StoreDecision, ctx: StoreContext) -> str:
    """Create (or re-use our own orphaned) store entry for ``ctx.link``.
    Returns the entry path. The link is not touched."""
    import time
    root = ensure_store_root(decision)
    for name in (mangle(ctx.link), hashed_name(ctx.link, ctx.host, ctx.uid)):
        entry = os.path.join(root, name)
        try:
            os.mkdir(entry)
        except FileExistsError:
            # Another process may be mid-creation; give it a moment to write
            # its metadata before deciding whose entry this is.
            meta = read_meta(entry)
            for _ in range(20):
                if meta is not None:
                    break
                time.sleep(0.1)
                meta = read_meta(entry)
            if meta is not None and meta.owned_by(ctx.link, ctx.host, ctx.uid):
                _log.debug("Re-using store entry %s", entry)
                touch_meta(entry, meta)
                return entry
            continue
        except OSError as e:
            raise RundirError("Failed to create rundir store entry %s: %s"
                              % (entry, e))
        write_meta(entry, _new_meta(ctx, decision.provenance))
        _log.debug("Created store entry %s", entry)
        return entry
    raise RundirError("Cannot find a free entry name for %s in store %s"
                      % (ctx.link, root))


def _lock_session(info: RundirInfo):
    lk = entry_lock(info.entry, shared=True)
    try:
        if not lk.acquire(blocking=False):
            print("Note: rundir store entry %s is locked by a store "
                  "operation; waiting..." % info.entry, file=sys.stderr)
            lk.acquire(blocking=True)
    except OSError as e:
        _log.warning("Cannot lock rundir entry %s: %s", info.entry, e)
        return
    info.lock = lk


def _check_mismatch(info: RundirInfo):
    d = info.store
    if d is None or info.entry is None:
        return
    here = os.path.realpath(os.path.dirname(info.entry))
    want = os.path.realpath(d.root) if d.is_store else None
    if want != here:
        info.mismatch = True
        _log.debug("rundir %s is in %s, but the configured store is %s (%s)",
                   info.path, here, want or "local", d.provenance)


# ---------------------------------------------------------------- inspect

def inspect_rundir(link: str) -> RundirInfo:
    """Describe the rundir at ``link`` without changing anything."""
    pkg_root = os.path.dirname(link)
    if os.path.islink(link):
        if not os.path.exists(link):
            return RundirInfo(link, pkg_root, "dangling", entry=_abs_target(link))
        entry = os.path.realpath(link)
        if not os.path.isdir(entry):
            return RundirInfo(link, pkg_root, "file", entry=entry)
        meta = read_meta(entry)
        if meta is None:
            return RundirInfo(link, pkg_root, "unmanaged-symlink", entry=entry)
        if meta.link == link or _same_link(meta.link, link):
            state = "ok"
        elif link_targets_entry(meta.link, entry):
            state = "copied"
        else:
            state = "moved"
        return RundirInfo(link, pkg_root, state, entry=entry, meta=meta)
    if os.path.isdir(link):
        return RundirInfo(link, pkg_root, "local")
    if os.path.lexists(link):
        return RundirInfo(link, pkg_root, "file")
    return RundirInfo(link, pkg_root, "none")


# ---------------------------------------------------------------- resolve

def resolve_rundir(pkg_root: Optional[str], *, create: bool = True,
                   args=None, package: Optional[str] = None,
                   store: Optional[StoreDecision] = None,
                   recreate: Optional[bool] = None,
                   cwd: Optional[str] = None,
                   lock: bool = True) -> RundirInfo:
    """Resolve the rundir for the project rooted at ``pkg_root``.

    With ``create=False`` this only computes the path (nothing on disk is
    created or modified); display-only commands use it. With ``create=True``
    the rundir, store entry and link are created as needed, a dangling link is
    recovered, and a shared session lock is taken on a store entry.

    ``args`` supplies the CLI store options (``store``, ``no_store``,
    ``store_recreate``) when present.
    """
    cwd = cwd or os.getcwd()
    link = rundir_path(pkg_root, cwd)
    if not create:
        return RundirInfo(link, pkg_root, "none")

    _check_location(pkg_root, cwd)
    base = os.path.dirname(link)

    ctx = make_context(link, base, package)
    if store is None:
        store = resolve_store(
            ctx, base,
            cli_store=getattr(args, "store", None),
            cli_no_store=bool(getattr(args, "no_store", False)))
    if recreate is None:
        recreate = bool(getattr(args, "store_recreate", False)) or \
            os.environ.get("DFM_STORE_RECREATE", "") in ("1", "true", "yes")

    info = _resolve(link, base, ctx, store, recreate)
    info.store = store
    if info.entry is not None and info.meta is not None:
        _check_mismatch(info)
        if lock:
            _lock_session(info)
            if not os.path.isdir(info.entry):
                # Removed (gc) while we waited for the lock.
                info.close()
                info = _resolve(link, base, ctx, store, recreate)
                info.store = store
                if lock and info.entry is not None and info.meta is not None:
                    _lock_session(info)
    return info


def _resolve(link, base, ctx, store: StoreDecision, recreate: bool) -> RundirInfo:
    if os.path.islink(link):
        if os.path.exists(link):
            entry = os.path.realpath(link)
            if not os.path.isdir(entry):
                raise RundirError("%s is a symlink to %s, which is not a directory"
                                  % (link, entry))
            return _use_symlink(link, base, entry, ctx, store)
        return _dangling(link, base, ctx, store, recreate)
    if os.path.isdir(link):
        if store.is_store:
            _note_once("migrate:" + link,
                       "Note: a rundir store is configured (%s, from %s), but %s "
                       "is a local directory. Run 'dfm store migrate' to move "
                       "it into the store." % (store.root, store.provenance, link))
        return RundirInfo(link, base, "local")
    if os.path.lexists(link):
        raise RundirError("%s exists but is not a directory or a symlink to one"
                          % link)
    if store.is_store:
        entry = create_entry(store, ctx)
        atomic_symlink(entry, link)
        _gitignore_check(base)
        return RundirInfo(link, base, "ok", entry=entry, meta=read_meta(entry))
    os.makedirs(link, exist_ok=True)
    return RundirInfo(link, base, "local")


def _use_symlink(link, base, entry, ctx, store) -> RundirInfo:
    meta = read_meta(entry)
    if meta is None:
        if is_store_root(os.path.dirname(entry)):
            # In a store, but no metadata (e.g. hand-copied): adopt it.
            meta = _new_meta(ctx, "adopted")
            try:
                write_meta(entry, meta)
            except OSError as e:
                _log.warning("Cannot write metadata in %s: %s", entry, e)
                return RundirInfo(link, base, "unmanaged-symlink", entry=entry)
            return RundirInfo(link, base, "ok", entry=entry, meta=meta)
        # A hand-made symlink outside any store: use as-is.
        return RundirInfo(link, base, "unmanaged-symlink", entry=entry)

    if meta.link == link or _same_link(meta.link, link):
        touch_meta(entry, meta, host=ctx.host)
        return RundirInfo(link, base, "ok", entry=entry, meta=meta)

    if link_targets_entry(meta.link, entry):
        # Copied project: both links point at one entry. Fork.
        print("Warning: %s shares its rundir store entry with %s (was the "
              "project copied?). Creating a fresh rundir for this copy."
              % (link, meta.link), file=sys.stderr)
        fork_store = store if store.is_store else StoreDecision(
            root=os.path.dirname(entry), provenance="fork:%s" % meta.link)
        new_entry = create_entry(fork_store, ctx)
        atomic_symlink(new_entry, link)
        return RundirInfo(link, base, "ok", entry=new_entry,
                          meta=read_meta(new_entry))

    # Moved project: adopt the entry.
    return _adopt(link, base, entry, meta, ctx)


def _adopt(link, base, entry, meta: EntryMeta, ctx) -> RundirInfo:
    old_link = meta.link
    meta.link = ctx.link
    meta.project_root = ctx.project_root
    meta.package = ctx.package or meta.package
    meta.host = ctx.host
    new_entry = entry
    root = os.path.dirname(entry)
    lk = entry_lock(entry, shared=False)
    if lk.acquire(blocking=False):
        try:
            want = os.path.join(root, mangle(link))
            if want != entry and not os.path.lexists(want):
                try:
                    os.rename(entry, want)
                    new_entry = want
                except OSError as e:
                    _log.debug("Could not rename %s -> %s: %s", entry, want, e)
            touch_meta(new_entry, meta)
        finally:
            lk.release()
    else:
        touch_meta(entry, meta)
    if new_entry != entry:
        atomic_symlink(new_entry, link)
    _log.info("Adopted rundir store entry %s (moved from %s)", new_entry, old_link)
    return RundirInfo(link, base, "ok", entry=new_entry, meta=meta)


def _dangling(link, base, ctx, store: StoreDecision, recreate: bool) -> RundirInfo:
    target = _abs_target(link)
    parent = os.path.dirname(target)
    if recreate and store.is_store:
        entry = create_entry(store, ctx)
        atomic_symlink(entry, link)
        print("Note: %s was dangling (-> %s); re-created it in store %s"
              % (link, target, store.root), file=sys.stderr)
        return RundirInfo(link, base, "ok", entry=entry, meta=read_meta(entry))
    if os.path.isdir(parent):
        try:
            os.mkdir(target)
        except FileExistsError:
            pass
        except OSError as e:
            raise RundirError("rundir %s -> %s is dangling, and re-creating "
                              "the target failed: %s" % (link, target, e))
        meta = None
        if is_store_root(parent):
            meta = read_meta(target)
            if meta is None:
                meta = _new_meta(ctx, "recreated")
                write_meta(target, meta)
        print("Note: rundir entry %s was missing; recreated (previous results "
              "are gone)" % target, file=sys.stderr)
        state = "ok" if meta is not None else "unmanaged-symlink"
        return RundirInfo(link, base, state, entry=target, meta=meta)
    hint = []
    hint.append("  - Mount the store, or")
    if store.is_store:
        hint.append("  - dfm store relink            (re-create in the "
                    "configured store, %s), or" % store.root)
        hint.append("  - run with --store-recreate   (same, non-interactively), or")
    hint.append("  - dfm store unlink --local    (replace the link with a "
                "local rundir)")
    raise RundirError("rundir -> %s, but %s does not exist.\n%s"
                      % (target, parent, "\n".join(hint)))


def _gitignore_check(base: str):
    """Warn once if `rundir` (the symlink) is not git-ignored. `rundir/` in
    .gitignore matches only a directory, not a symlink."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", base, "check-ignore", "-q", RUNDIR_NAME],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=2)
    except (OSError, subprocess.SubprocessError):
        return
    if r.returncode == 1:
        _note_once("gitignore:" + base,
                   "Note: %s is not ignored by git. Add 'rundir' (no trailing "
                   "slash -- 'rundir/' does not match a symlink) to .gitignore."
                   % os.path.join(base, RUNDIR_NAME))
