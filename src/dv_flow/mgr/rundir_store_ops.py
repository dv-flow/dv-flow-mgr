"""Rundir store operations behind the `dfm store` commands: listing, gc,
migrate, unlink and relink. See RUNDIR_STORE_DESIGN.md §8."""
import dataclasses as dc
import datetime
import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from .rundir_store import (
    RundirError, create_entry, clean_rundir, inspect_rundir, make_context,
    rundir_path, _gitignore_check)
from .rundir_store_entry import (
    EntryRecord, KEEP_FILES, STORE_LOCK, EntryLock, Status, classify,
    entry_lock, is_store_root, measure, parse_iso, read_meta, read_stats,
    remove_entry, scan_store, stats_stale, write_meta, write_stats)
from .site_config import current_host
from .store_config import StoreDecision
from .util.atomic import atomic_symlink

_log = logging.getLogger("RundirStore")

RECENT_SECS = 3600


# ---------------------------------------------------------------- helpers

_DUR_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhdw]?)\s*$")
_DUR_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "": 86400}


def parse_duration(s: str) -> float:
    """'30d', '12h', '2w', '90m', '45s'; a bare number means days."""
    m = _DUR_RE.match(s or "")
    if m is None:
        raise ValueError("Invalid duration '%s' (expected e.g. 30d, 12h, 2w)" % s)
    return float(m.group(1)) * _DUR_UNITS[m.group(2)]


def age_secs(meta, now: Optional[datetime.datetime] = None) -> Optional[float]:
    if meta is None:
        return None
    t = parse_iso(meta.last_used) or parse_iso(meta.created)
    if t is None:
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return (now - t).total_seconds()


def same_fs(a: str, b: str) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def move_contents(src: str, dst: str):
    """Move everything in ``src`` (except store metadata/lock) into ``dst``.
    Uses rename on the same filesystem, else copy-then-delete. On failure,
    renamed children are moved back before re-raising."""
    if same_fs(src, dst):
        moved = []
        try:
            for de in sorted(os.scandir(src), key=lambda d: d.name):
                if de.name in KEEP_FILES:
                    continue
                to = os.path.join(dst, de.name)
                os.rename(de.path, to)
                moved.append((to, de.path))
        except BaseException:
            for to, frm in reversed(moved):
                try:
                    os.rename(to, frm)
                except OSError:
                    pass
            raise
        return
    names = []
    try:
        for de in sorted(os.scandir(src), key=lambda d: d.name):
            if de.name in KEEP_FILES:
                continue
            to = os.path.join(dst, de.name)
            if de.is_dir(follow_symlinks=False):
                shutil.copytree(de.path, to, symlinks=True)
            else:
                shutil.copy2(de.path, to, follow_symlinks=False)
            names.append(de.name)
    except BaseException:
        for n in names:
            p = os.path.join(dst, n)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.unlink(p)
                except OSError:
                    pass
        raise
    for n in names:
        p = os.path.join(src, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        else:
            os.unlink(p)


def _owner_uid(path: str) -> Optional[int]:
    try:
        return os.stat(path).st_uid
    except OSError:
        return None


# ---------------------------------------------------------------- list / stats

SIZES_NONE = "none"          # no size information
SIZES_CACHED = "cached"      # only what .dfm-rundir-stats.json already has
SIZES_MEASURE = "measure"    # measure entries with no or stale cached size
SIZES_REFRESH = "refresh"    # re-measure everything

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtp]?)i?b?\s*$", re.I)
_SIZE_UNITS = {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30, "t": 1 << 40,
               "p": 1 << 50}


def parse_size(s: str) -> int:
    """'500M', '10G', '1.5T', '2GiB', '123' (bytes). Binary units."""
    m = _SIZE_RE.match(s or "")
    if m is None:
        raise ValueError("Invalid size '%s' (expected e.g. 500M, 10G, 1.5T)" % s)
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).lower()])


@dc.dataclass
class EntryFilter:
    user: Optional[str] = None
    all_users: bool = False
    statuses: List[str] = dc.field(default_factory=list)
    older_than: Optional[float] = None       # seconds since last use
    larger_than: Optional[int] = None        # bytes on disk
    package: Optional[str] = None            # glob
    host: Optional[str] = None               # glob

    def owner_ok(self, path: str, meta) -> bool:
        if self.all_users:
            return True
        if self.user is not None:
            if meta is not None and meta.user is not None:
                return meta.user == self.user
            import pwd
            uid = _owner_uid(path)
            try:
                return uid is not None and pwd.getpwuid(uid).pw_name == self.user
            except KeyError:
                return False
        uid = meta.uid if (meta is not None and meta.uid is not None) \
            else _owner_uid(path)
        return uid == os.getuid()

    def meta_ok(self, meta, now) -> bool:
        import fnmatch
        if self.package is not None:
            if meta is None or not fnmatch.fnmatchcase(meta.package or "", self.package):
                return False
        if self.host is not None:
            if meta is None or not fnmatch.fnmatchcase(meta.host or "", self.host):
                return False
        if self.older_than is not None:
            a = age_secs(meta, now)
            if a is None or a < self.older_than:
                return False
        return True


def _attach_stats(recs: List[EntryRecord], mode: str, workers: int = 8):
    if mode == SIZES_NONE or not recs:
        return
    todo = []
    for r in recs:
        st = None if mode == SIZES_REFRESH else read_stats(r.path)
        r.stats = st
        r.stats_stale = stats_stale(st, r.meta)
        if mode == SIZES_REFRESH or (mode == SIZES_MEASURE and (st is None or r.stats_stale)):
            todo.append(r)
    if not todo:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r, st in zip(todo, ex.map(lambda r: measure(r.path), todo)):
            r.stats = st
            r.stats_stale = False
            write_stats(r.path, st)


def list_entries(root: str, flt: Optional[EntryFilter] = None,
                 sizes: str = SIZES_NONE, this_host: Optional[str] = None,
                 with_size: bool = False, workers: int = 8,
                 now: Optional[datetime.datetime] = None) -> List[EntryRecord]:
    """Entries in ``root`` that pass ``flt``, classified, with sizes per
    ``sizes``. A ``larger_than`` filter implies at least SIZES_MEASURE."""
    flt = flt or EntryFilter()
    this_host = this_host or current_host()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if with_size and sizes == SIZES_NONE:
        sizes = SIZES_MEASURE
    if flt.larger_than is not None and sizes in (SIZES_NONE, SIZES_CACHED):
        sizes = SIZES_MEASURE
    recs = []
    for path in scan_store(root):
        meta = read_meta(path)
        if not flt.owner_ok(path, meta) or not flt.meta_ok(meta, now):
            continue
        st = classify(path, this_host, meta=meta)
        if flt.statuses and st.value not in flt.statuses:
            continue
        recs.append(EntryRecord(os.path.basename(path), path, meta, st))
    _attach_stats(recs, sizes, workers)
    if flt.larger_than is not None:
        recs = [r for r in recs if (r.size or 0) >= flt.larger_than]
    return recs


def fs_usage(root: str) -> Optional[Dict[str, int]]:
    try:
        v = os.statvfs(root)
    except OSError:
        return None
    total = v.f_blocks * v.f_frsize
    free = v.f_bavail * v.f_frsize
    return {"total": total, "free": free, "used": total - v.f_bfree * v.f_frsize}


AGE_BUCKETS = [("<1d", 86400), ("1-7d", 7 * 86400), ("7-30d", 30 * 86400),
               ("30-90d", 90 * 86400), (">90d", None)]


def age_bucket(secs: Optional[float]) -> str:
    if secs is None:
        return "unknown"
    for name, lim in AGE_BUCKETS:
        if lim is None or secs < lim:
            return name
    return AGE_BUCKETS[-1][0]


def project_key(meta) -> str:
    """Group entries by git org/repo, else package, else '?'."""
    if meta is None:
        return "(unmanaged)"
    from .site_config import parse_git_org_repo
    org, repo = parse_git_org_repo((meta.git or {}).get("remote"))
    if repo:
        return "%s/%s" % (org, repo) if org else repo
    return meta.package or "?"


def _group(recs, keyf) -> List[Dict[str, Any]]:
    g: Dict[str, Dict[str, Any]] = {}
    for r in recs:
        k = keyf(r)
        e = g.setdefault(k, {"key": k, "count": 0, "size": 0, "sized": 0})
        e["count"] += 1
        if r.size is not None:
            e["size"] += r.size
            e["sized"] += 1
    return sorted(g.values(), key=lambda e: (-e["size"], -e["count"], e["key"]))


def aggregate(recs: List[EntryRecord], root: str,
              cands: Optional[List["Candidate"]] = None, top: int = 10,
              now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Store-level statistics (see design §8.3)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    sized = [r for r in recs if r.size is not None]
    by_age = {e["key"]: e for e in _group(
        recs, lambda r: age_bucket(age_secs(r.meta, now)))}
    ages = [{"key": n, "count": by_age.get(n, {}).get("count", 0),
             "size": by_age.get(n, {}).get("size", 0)}
            for n, _ in AGE_BUCKETS]
    if "unknown" in by_age:
        ages.append(by_age["unknown"])
    data = {
        "store": root,
        "filesystem": fs_usage(root),
        "entries": len(recs),
        "sized": len(sized),
        "size": sum(r.size for r in sized),
        "stale_sizes": sum(1 for r in sized if r.stats_stale),
        "users": len({(r.meta.user if r.meta else None) for r in recs}),
        "by_status": _group(recs, lambda r: r.status.value),
        "by_last_used": ages,
        "by_user": _group(recs, lambda r: (r.meta.user if r.meta else None) or "?"),
        "by_host": _group(recs, lambda r: (r.meta.host if r.meta else None) or "?"),
        "by_project": _group(recs, lambda r: project_key(r.meta)),
        "largest": [r.name for r in sorted(sized, key=lambda r: -r.size)[:top]],
    }
    if cands is not None:
        tiers = {}
        for c in cands:
            t = tiers.setdefault(c.tier, {"tier": c.tier, "count": 0, "size": 0})
            t["count"] += 1
            t["size"] += c.rec.size or 0
        data["reclaimable"] = [tiers[t] for t in ("safe", "review") if t in tiers]
    return data


# ---------------------------------------------------------------- candidates

TIER_SAFE = "safe"
TIER_REVIEW = "review"
DEFAULT_STALE = 30 * 86400


@dc.dataclass
class Candidate:
    rec: EntryRecord
    tier: str        # safe | review
    kind: str        # orphan | retargeted | unknown | stale
    reason: str

    def to_dict(self, now=None) -> Dict[str, Any]:
        d = self.rec.to_dict(now)
        d.update(tier=self.tier, kind=self.kind, reason=self.reason)
        return d


def find_candidates(recs: List[EntryRecord], stale_secs: float = DEFAULT_STALE,
                    force: bool = False,
                    now: Optional[datetime.datetime] = None) -> List[Candidate]:
    """Rank entries worth deleting: safe ones (project gone) and ones to
    review (unverifiable, or unused for ``stale_secs``). Biggest first."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    out = []
    for r in recs:
        st = r.status
        age = age_secs(r.meta, now)
        if st in (Status.BUSY, Status.UNMANAGED):
            continue
        if not force and age is not None and age < RECENT_SECS:
            continue
        if st == Status.ORPHAN:
            c = Candidate(r, TIER_SAFE, "orphan", "project deleted")
        elif st == Status.RETARGETED:
            c = Candidate(r, TIER_SAFE, "retargeted",
                          "project no longer links here")
        elif st == Status.UNKNOWN:
            c = Candidate(r, TIER_REVIEW, "unknown",
                          "not visible from this host; last used on %s" % r.meta.host)
        elif st == Status.OK and age is not None and age >= stale_secs:
            c = Candidate(r, TIER_REVIEW, "stale",
                          "project exists; unused %s (results would be lost)"
                          % fmt_age(age))
        else:
            continue
        out.append(c)
    out.sort(key=lambda c: (-(c.rec.size or 0), -(age_secs(c.rec.meta, now) or 0)))
    return out


# ---------------------------------------------------------------- gc

@dc.dataclass
class GcCandidate:
    rec: EntryRecord
    reason: str


@dc.dataclass
class GcPlan:
    delete: List[GcCandidate] = dc.field(default_factory=list)
    skipped: List[GcCandidate] = dc.field(default_factory=list)
    errors: List[str] = dc.field(default_factory=list)
    need: Optional[int] = None       # bytes to reclaim (--reclaim/--target-free)

    @property
    def size(self) -> int:
        return sum(c.rec.size or 0 for c in self.delete)


def read_selection(text: str) -> List[str]:
    """Entry identifiers from a --from file: one per line, '#' comments.
    The first whitespace-separated field is used, so table-ish lines work."""
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.split()[0])
    return out


def resolve_selection(root: str, ids: List[str], recs: List[EntryRecord]
                      ) -> Tuple[List[EntryRecord], List[str]]:
    """Map names, entry paths or link paths to records."""
    by_name = {r.name: r for r in recs}
    by_link = {r.meta.link: r for r in recs if r.meta is not None}
    real_root = os.path.realpath(root)
    found, errors = [], []
    for i in ids:
        r = by_name.get(i) or by_link.get(os.path.abspath(i) if os.sep in i else i)
        if r is None and os.sep in i:
            rp = os.path.realpath(i)
            if os.path.dirname(rp) == real_root:
                r = by_name.get(os.path.basename(rp))
        if r is None:
            errors.append("%s: no such entry in %s" % (i, root))
        elif r not in found:
            found.append(r)
    return found, errors


def plan_gc(root: str, flt: EntryFilter, orphans: bool = False,
            older_than: Optional[float] = None, include_unknown: bool = False,
            force: bool = False, this_host: Optional[str] = None,
            selection: Optional[List[str]] = None,
            reclaim: Optional[int] = None, target_free: Optional[int] = None,
            sizes: str = SIZES_NONE) -> GcPlan:
    """Select entries for deletion (§8.1, §8.3).

    With an explicit ``selection`` (names/links/paths) the status criteria
    are skipped. Otherwise, with no criteria, means ``orphans``.
    ``older_than`` is in seconds. ``reclaim`` / ``target_free`` (bytes) trim
    the selection to the least-recently-used entries needed to free that
    much."""
    plan = GcPlan()
    if target_free is not None:
        fs = fs_usage(root)
        need = target_free - (fs["free"] if fs else 0)
        plan.need = max(need, 0)
        if need <= 0:
            return plan
        reclaim = need if reclaim is None else max(reclaim, need)
    elif reclaim is not None:
        plan.need = reclaim
    if reclaim is not None and sizes in (SIZES_NONE, SIZES_CACHED):
        sizes = SIZES_MEASURE
    now = datetime.datetime.now(datetime.timezone.utc)

    if selection is not None:
        sel_flt = dc.replace(flt, statuses=[], older_than=None)
        if not sel_flt.user:
            sel_flt.all_users = True   # resolve any entry; owner checked below
        recs = list_entries(root, sel_flt, sizes=sizes, this_host=this_host, now=now)
        chosen, plan.errors = resolve_selection(root, selection, recs)
        for r in chosen:
            if r.status == Status.BUSY:
                plan.skipped.append(GcCandidate(r, "busy"))
            elif not flt.all_users and not EntryFilter(user=flt.user).owner_ok(r.path, r.meta):
                plan.skipped.append(GcCandidate(r, "another user's entry (use --all-users)"))
            elif not force and (age_secs(r.meta, now) or RECENT_SECS) < RECENT_SECS:
                plan.skipped.append(GcCandidate(r, "used within the last hour"))
            else:
                plan.delete.append(GcCandidate(r, "selected"))
    else:
        if not orphans and older_than is None and reclaim is None:
            orphans = True
        recs = list_entries(root, flt, sizes=sizes, this_host=this_host, now=now)
        for rec in recs:
            st = rec.status
            if st in (Status.BUSY, Status.UNMANAGED):
                if st == Status.BUSY:
                    plan.skipped.append(GcCandidate(rec, "busy"))
                continue
            orphan_ok = st in (Status.ORPHAN, Status.RETARGETED) or \
                (include_unknown and st == Status.UNKNOWN)
            age = age_secs(rec.meta, now)
            old_ok = older_than is not None and age is not None and age >= older_than
            if orphans and older_than is not None:
                sel = orphan_ok and old_ok
                reason = "project gone; unused %s" % fmt_age(age)
            elif orphans:
                sel = orphan_ok
                reason = {Status.ORPHAN: "project deleted",
                          Status.RETARGETED: "project no longer links here",
                          Status.UNKNOWN: "not visible from this host"}.get(st, st.value)
            elif older_than is not None:
                sel = old_ok
                reason = "unused %s" % fmt_age(age)
            else:   # --reclaim/--target-free alone: any entry, LRU first
                sel = True
                reason = {Status.ORPHAN: "project deleted",
                          Status.RETARGETED: "project no longer links here"}.get(
                    st, "least recently used (%s)" % fmt_age(age))
            if not sel:
                continue
            if not force and age is not None and age < RECENT_SECS:
                plan.skipped.append(GcCandidate(rec, "used within the last hour"))
                continue
            plan.delete.append(GcCandidate(rec, reason))

    if reclaim is not None:
        # Orphans first, then least recently used, until enough is freed.
        def _k(c):
            dead = c.rec.status in (Status.ORPHAN, Status.RETARGETED)
            return (0 if dead else 1, -(age_secs(c.rec.meta, now) or 0))
        ordered = sorted(plan.delete, key=_k)
        keep, got = [], 0
        for c in ordered:
            if got >= reclaim:
                break
            keep.append(c)
            got += c.rec.size or 0
        plan.delete = keep
        if got < reclaim:
            plan.errors.append("selection frees only %s of the %s requested"
                               % (fmt_size(got), fmt_size(reclaim)))
    return plan


def execute_gc(root: str, plan: GcPlan, this_host: Optional[str] = None
               ) -> Tuple[List[GcCandidate], List[Tuple[GcCandidate, str]]]:
    """Delete the planned entries. Each entry is re-checked under an
    exclusive lock just before removal. Returns (removed, failed)."""
    this_host = this_host or current_host()
    removed, failed = [], []
    for c in plan.delete:
        lk = entry_lock(c.rec.path, shared=False)
        try:
            if not lk.acquire(blocking=False):
                failed.append((c, "busy"))
                continue
        except OSError as e:
            failed.append((c, str(e)))
            continue
        try:
            meta = read_meta(c.rec.path)
            st = classify(c.rec.path, this_host, meta=meta, check_busy=False)
            if st != c.rec.status:
                failed.append((c, "status changed to %s" % st.value))
                continue
            remove_entry(c.rec.path)
            removed.append(c)
        except OSError as e:
            failed.append((c, str(e)))
        finally:
            lk.release()
    return removed, failed


def store_lock(root: str) -> EntryLock:
    return EntryLock(os.path.join(root, STORE_LOCK), shared=False)


def fmt_age(secs: Optional[float]) -> str:
    if secs is None:
        return "?"
    if secs < 3600:
        return "%dm" % (secs // 60)
    if secs < 86400:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)


def fmt_size(n: Optional[int]) -> str:
    if n is None:
        return "-"
    n = float(n)
    for unit in ("B", "K", "M", "G", "T", "P"):
        if abs(n) < 1024 or unit == "P":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0
    return str(n)


# ---------------------------------------------------------------- lifecycle

def _lock_entry_exclusive(entry: str) -> EntryLock:
    lk = entry_lock(entry, shared=False)
    if not lk.acquire(blocking=False):
        raise RundirError("Rundir entry %s is in use (a dfm session is "
                          "running); try again when it finishes" % entry)
    return lk


def migrate_rundir(pkg_root: str, decision: StoreDecision,
                   package: Optional[str] = None, dry_run: bool = False) -> str:
    """Turn a local ``<pkg_root>/rundir`` into a store entry plus symlink.
    Returns the entry path (or the planned store root with ``dry_run``)."""
    link = rundir_path(pkg_root)
    info = inspect_rundir(link)
    if info.state != "local":
        raise RundirError("%s is not a local rundir (state: %s); nothing to "
                          "migrate" % (link, info.state))
    if not decision.is_store:
        raise RundirError("No rundir store is configured. Set DFM_STORE, add "
                          "'store: {root: ...}' to your user config, or pass "
                          "--store DIR")
    if dry_run:
        return decision.root
    ctx = make_context(link, pkg_root, package)
    entry = create_entry(decision, ctx)
    lk = _lock_entry_exclusive(entry)
    try:
        clean_rundir(entry)
        move_contents(link, entry)
        aside = "%s.migrating.%d" % (link, os.getpid())
        os.rename(link, aside)
        try:
            atomic_symlink(entry, link)
        except BaseException:
            os.rename(aside, link)
            move_contents(entry, link)
            raise
        shutil.rmtree(aside, ignore_errors=True)
    finally:
        lk.release()
    _gitignore_check(pkg_root)
    return entry


def unlink_rundir(pkg_root: str, local: bool = False, keep: bool = False
                  ) -> Optional[str]:
    """Remove the rundir link. With ``local``, move the contents back into a
    real directory. Unless ``keep``, the store entry is deleted. Returns the
    entry path it pointed at (if any)."""
    link = rundir_path(pkg_root)
    info = inspect_rundir(link)
    if info.state in ("local", "none", "file"):
        raise RundirError("%s is not a rundir link (state: %s)" % (link, info.state))
    if info.state == "dangling":
        os.unlink(link)
        if local:
            os.mkdir(link)
        return info.entry
    entry = info.entry
    lk = _lock_entry_exclusive(entry) if info.meta is not None else None
    try:
        if local:
            tmp = "%s.unlinking.%d" % (link, os.getpid())
            os.mkdir(tmp)
            try:
                move_contents(entry, tmp)
            except BaseException:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            os.unlink(link)
            os.rename(tmp, link)
        else:
            os.unlink(link)
        if info.meta is not None and not keep:
            remove_entry(entry)
    finally:
        if lk is not None:
            lk.release()
    return entry


def relink_rundir(pkg_root: str, decision: StoreDecision,
                  package: Optional[str] = None) -> str:
    """Move the rundir's entry to the configured store, or re-create it there
    if the link is dangling. Returns the new entry path."""
    link = rundir_path(pkg_root)
    if not decision.is_store:
        raise RundirError("No rundir store is configured; use --store DIR, or "
                          "'dfm store unlink --local' for a local rundir")
    info = inspect_rundir(link)
    if info.state == "local":
        raise RundirError("%s is a local rundir; use 'dfm store migrate'" % link)
    if info.state == "file":
        raise RundirError("%s is not a directory or a symlink to one" % link)
    ctx = make_context(link, pkg_root, package)
    if info.state in ("none", "dangling"):
        entry = create_entry(decision, ctx)
        atomic_symlink(entry, link)
        return entry
    old = info.entry
    if os.path.realpath(os.path.dirname(old)) == os.path.realpath(decision.root):
        return old
    lk = _lock_entry_exclusive(old) if info.meta is not None else None
    try:
        entry = create_entry(decision, ctx)
        clean_rundir(entry)
        move_contents(old, entry)
        meta = read_meta(entry)
        if meta is not None:
            meta.store_source = decision.provenance
            write_meta(entry, meta)
        atomic_symlink(entry, link)
        if info.meta is not None:
            remove_entry(old)
        else:
            _log.info("Left the previous (unmanaged) rundir target %s in place", old)
    finally:
        if lk is not None:
            lk.release()
    return entry
