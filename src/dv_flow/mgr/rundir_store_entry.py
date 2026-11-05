"""Rundir store entries: naming, metadata, locking and classification.

A store root holds one entry (a rundir) per project link::

    $STORE/
      .dfm-store.yaml            # marker
      .dfm-store.lock            # gc lock
      _home_u_proj_rundir/
        .dfm-rundir.json         # EntryMeta
        .dfm-rundir.lock         # shared flock held by a dfm session
        ...rundir contents...

See RUNDIR_STORE_DESIGN.md §4 and §8.
"""
import dataclasses as dc
import datetime
import enum
import errno
import hashlib
import json
import logging
import os
from typing import Any, Dict, Iterator, List, Optional

import yaml

from .util.atomic import atomic_write_text

_log = logging.getLogger("RundirStore")

MARKER = ".dfm-store.yaml"
STORE_LOCK = ".dfm-store.lock"
META = ".dfm-rundir.json"
ENTRY_LOCK = ".dfm-rundir.lock"
STATS = ".dfm-rundir-stats.json"
KEEP_FILES = (META, ENTRY_LOCK, STATS)

META_SCHEMA = 1
MAX_NAME = 200
TAIL_NAME = 160


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------- naming

def entry_hash(host: str, uid: int, link: str) -> str:
    return hashlib.sha1(("%s:%s:%s" % (host, uid, link)).encode()).hexdigest()[:8]


def mangle(link: str) -> str:
    """``/home/u/p/rundir`` -> ``_home_u_p_rundir``, kept to MAX_NAME bytes."""
    name = os.path.abspath(link).replace(os.sep, "_")
    b = name.encode("utf-8", "surrogateescape")
    if len(b) > MAX_NAME:
        h = hashlib.sha1(b).hexdigest()[:8]
        tail = b[-TAIL_NAME:].decode("utf-8", "ignore")
        name = "%s__%s" % (tail, h)
    return name


def hashed_name(link: str, host: str, uid: int) -> str:
    base = mangle(link)
    suffix = "__" + entry_hash(host, uid, link)
    b = base.encode("utf-8", "surrogateescape")
    if len(b) + len(suffix) > MAX_NAME:
        base = b[-(MAX_NAME - len(suffix)):].decode("utf-8", "ignore")
    return base + suffix


# ---------------------------------------------------------------- metadata

@dc.dataclass
class EntryMeta:
    link: str
    project_root: str
    package: Optional[str] = None
    user: Optional[str] = None
    uid: Optional[int] = None
    host: Optional[str] = None
    git: Dict[str, Optional[str]] = dc.field(default_factory=dict)
    store_source: Optional[str] = None
    dfm_version: Optional[str] = None
    created: Optional[str] = None
    last_used: Optional[str] = None
    sessions: int = 0
    schema: int = META_SCHEMA

    def to_dict(self) -> Dict[str, Any]:
        return dc.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntryMeta":
        names = {f.name for f in dc.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def owned_by(self, link: str, host: str, uid: int) -> bool:
        """Identity used when choosing an entry name (§4.1)."""
        return self.link == link and self.uid == uid and self.host == host


def read_meta(entry: str) -> Optional[EntryMeta]:
    p = os.path.join(entry, META)
    try:
        with open(p) as fp:
            return EntryMeta.from_dict(json.load(fp))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as e:
        _log.warning("Unreadable rundir metadata %s: %s", p, e)
        return None


def write_meta(entry: str, meta: EntryMeta):
    atomic_write_text(os.path.join(entry, META),
                      json.dumps(meta.to_dict(), indent=2, sort_keys=True) + "\n")


def dfm_version() -> Optional[str]:
    try:
        from importlib.metadata import version
        return version("dv-flow-mgr")
    except Exception:
        return None


def touch_meta(entry: str, meta: EntryMeta, host: Optional[str] = None):
    """Update last_used (and host) and count the session; failures only
    warn."""
    meta.last_used = now_iso()
    meta.sessions = (meta.sessions or 0) + 1
    if host is not None:
        meta.host = host
    try:
        write_meta(entry, meta)
    except OSError as e:
        _log.warning("Failed to update rundir metadata in %s: %s", entry, e)


# ---------------------------------------------------------------- marker

def is_store_root(d: str) -> bool:
    return os.path.isfile(os.path.join(d, MARKER))


def read_marker(d: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(d, MARKER)
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as fp:
            data = yaml.safe_load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_marker(d: str, mode: str = "private"):
    atomic_write_text(os.path.join(d, MARKER), yaml.safe_dump(
        {"version": 1, "created": now_iso(), "mode": mode}, sort_keys=False),
        mode=0o644)


# ---------------------------------------------------------------- locking

class EntryLock:
    """A ``flock`` on a lock file. Shared for sessions, exclusive for gc and
    lifecycle commands. The fd is close-on-exec so tools never inherit it."""

    def __init__(self, path: str, shared: bool = True):
        self.path = path
        self.shared = shared
        self._fd: Optional[int] = None

    def acquire(self, blocking: bool = False) -> bool:
        import fcntl
        if self._fd is not None:
            return True
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o666)
        op = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
        if not blocking:
            op |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, op)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                return False
            raise
        self._fd = fd
        return True

    def release(self):
        if self._fd is not None:
            import fcntl
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self):
        if not self.acquire(blocking=False):
            raise BlockingIOError("lock busy: %s" % self.path)
        return self

    def __exit__(self, *a):
        self.release()


def entry_lock(entry: str, shared: bool = True) -> EntryLock:
    return EntryLock(os.path.join(entry, ENTRY_LOCK), shared=shared)


def is_busy(entry: str) -> bool:
    lk = entry_lock(entry, shared=False)
    try:
        if lk.acquire(blocking=False):
            lk.release()
            return False
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- classification

class Status(enum.Enum):
    OK = "ok"
    ORPHAN = "orphan"
    RETARGETED = "retargeted"
    UNKNOWN = "unknown"
    BUSY = "busy"
    UNMANAGED = "unmanaged"


@dc.dataclass
class EntryStats:
    """Result of walking an entry's tree. ``disk`` is allocated bytes (what
    deleting it frees), ``apparent`` the sum of file sizes."""
    disk: int = 0
    apparent: int = 0
    files: int = 0
    dirs: int = 0
    last_modified: Optional[str] = None
    top: List[List[Any]] = dc.field(default_factory=list)   # [[name, disk], ...]
    measured: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dc.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntryStats":
        names = {f.name for f in dc.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


TOP_N = 10


def measure(entry: str) -> EntryStats:
    """Walk ``entry`` without following symlinks. Hard-linked files are
    counted once."""
    seen = set()
    st = EntryStats()
    newest = 0.0
    top: Dict[str, int] = {}

    def walk(d: str, bucket: Optional[str]):
        nonlocal newest
        try:
            it = list(os.scandir(d))
        except OSError:
            return
        for de in it:
            if bucket is None and de.name in KEEP_FILES:
                continue
            b = bucket if bucket is not None else de.name
            try:
                s_ = de.stat(follow_symlinks=False)
            except OSError:
                continue
            if s_.st_mtime > newest:
                newest = s_.st_mtime
            if de.is_dir(follow_symlinks=False):
                st.dirs += 1
                blk = getattr(s_, "st_blocks", 0) * 512
                st.disk += blk
                top[b] = top.get(b, 0) + blk
                walk(de.path, b)
                continue
            if s_.st_nlink > 1:
                key = (s_.st_dev, s_.st_ino)
                if key in seen:
                    continue
                seen.add(key)
            st.files += 1
            st.apparent += s_.st_size
            blk = getattr(s_, "st_blocks", 0) * 512
            st.disk += blk
            top[b] = top.get(b, 0) + blk
    walk(entry, None)
    if newest:
        st.last_modified = datetime.datetime.fromtimestamp(
            newest, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    st.top = [[n, v] for n, v in sorted(top.items(), key=lambda x: -x[1])[:TOP_N]]
    st.measured = now_iso()
    return st


def read_stats(entry: str) -> Optional[EntryStats]:
    try:
        with open(os.path.join(entry, STATS)) as fp:
            return EntryStats.from_dict(json.load(fp))
    except (OSError, ValueError, TypeError):
        return None


def write_stats(entry: str, stats: EntryStats):
    try:
        atomic_write_text(os.path.join(entry, STATS),
                          json.dumps(stats.to_dict(), sort_keys=True) + "\n")
    except OSError:
        pass     # e.g. another user's entry: the cache is best-effort


def stats_stale(stats: Optional[EntryStats], meta: Optional[EntryMeta]) -> bool:
    """True if the entry was used after it was measured."""
    if stats is None:
        return True
    m = parse_iso(stats.measured)
    u = parse_iso(meta.last_used) if meta is not None else None
    return m is None or (u is not None and u > m)


@dc.dataclass
class EntryRecord:
    name: str
    path: str
    meta: Optional[EntryMeta]
    status: Status
    stats: Optional[EntryStats] = None
    stats_stale: bool = False

    @property
    def size(self) -> Optional[int]:
        return self.stats.disk if self.stats is not None else None

    def to_dict(self, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        m = self.meta

        def _age(ts):
            t = parse_iso(ts)
            return None if t is None else int((now - t).total_seconds())
        return {
            "name": self.name,
            "path": self.path,
            "status": self.status.value,
            "link": m.link if m else None,
            "project_root": m.project_root if m else None,
            "package": m.package if m else None,
            "user": m.user if m else None,
            "host": m.host if m else None,
            "git": m.git if m else None,
            "created": m.created if m else None,
            "created_age_s": _age(m.created) if m else None,
            "last_used": m.last_used if m else None,
            "last_used_age_s": _age(m.last_used) if m else None,
            "sessions": m.sessions if m else None,
            "size": self.size,
            "apparent_size": self.stats.apparent if self.stats else None,
            "files": self.stats.files if self.stats else None,
            "last_modified": self.stats.last_modified if self.stats else None,
            "size_measured": self.stats.measured if self.stats else None,
            "size_stale": self.stats_stale if self.stats else None,
            "top": [{"name": n, "size": v} for n, v in self.stats.top]
                   if self.stats else None,
            "meta": m.to_dict() if m else None,
        }


def _same_dir(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def link_targets_entry(link: str, entry: str) -> bool:
    return os.path.islink(link) and _same_dir(link, entry)


def classify(entry: str, this_host: str, meta: Optional[EntryMeta] = None,
             check_busy: bool = True) -> Status:
    """Classify an entry (§8.1)."""
    if check_busy and is_busy(entry):
        return Status.BUSY
    if meta is None:
        meta = read_meta(entry)
    if meta is None:
        return Status.UNMANAGED
    link = meta.link
    if os.path.lexists(link):
        if link_targets_entry(link, entry):
            return Status.OK
        return Status.RETARGETED
    if meta.host == this_host or os.path.isdir(os.path.dirname(link)):
        return Status.ORPHAN
    return Status.UNKNOWN


def scan_store(root: str) -> Iterator[str]:
    """Yield the paths of entry directories in a store root."""
    try:
        it = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError as e:
        _log.warning("Cannot scan store %s: %s", root, e)
        return
    for de in it:
        if de.name.startswith("."):
            continue
        try:
            if de.is_dir(follow_symlinks=False):
                yield de.path
        except OSError:
            continue


def dir_size(path: str) -> int:
    """Total apparent size of files under ``path`` (no symlink following)."""
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for de in it:
                    try:
                        if de.is_dir(follow_symlinks=False):
                            stack.append(de.path)
                        else:
                            total += de.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def sizes(paths: List[str], workers: int = 8) -> Dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(zip(paths, ex.map(dir_size, paths)))


def remove_entry(entry: str):
    """Delete an entry: rename aside first (so a half-deleted entry is never
    mistaken for a live one), then remove the tree."""
    import shutil
    parent = os.path.dirname(entry)
    aside = os.path.join(parent, ".gc-%s-%d" % (os.path.basename(entry), os.getpid()))
    os.rename(entry, aside)
    shutil.rmtree(aside)
