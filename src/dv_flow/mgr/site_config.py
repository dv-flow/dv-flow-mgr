"""Site-level configuration hooks for dfm.

A site installs a Python package that registers a :class:`SiteConfig`
subclass (or a zero-argument factory returning one) under the entry-point
group ``dv_flow.mgr.site_config``::

    [project.entry-points."dv_flow.mgr.site_config"]
    acme = "acme_dfm.site:AcmeSiteConfig"

Exactly one site config is active. It is chosen by ``DFM_SITE_CONFIG_NAME``,
then the ``site-config:`` key in the user or site config file, then the last
one registered. The shape follows ivpm's ``SiteConfigRgy``, but this registry
is independent of ivpm.
"""
import dataclasses as dc
import getpass
import logging
import os
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("SiteConfig")

ENTRY_POINT_GROUP = "dv_flow.mgr.site_config"


def _git(root: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "-C", root] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


_GIT_URL_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")


def parse_git_org_repo(url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split a remote URL (scp-style, https, ssh://) into (org, repo)."""
    if not url:
        return None, None
    m = _GIT_URL_RE.search(url)
    if m is None:
        return None, None
    return m.group(1), m.group(2)


def current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return str(os.getuid())


def current_host() -> str:
    return socket.gethostname().split(".")[0]


@dc.dataclass(frozen=True)
class StoreContext:
    """Facts about the project whose rundir is being placed.

    Git facts are gathered lazily, on first use, and cached."""
    link: str
    project_root: str
    package: Optional[str] = None
    user: str = dc.field(default_factory=current_user)
    uid: int = dc.field(default_factory=os.getuid)
    host: str = dc.field(default_factory=current_host)
    _cache: Dict[str, Any] = dc.field(default_factory=dict, compare=False,
                                      repr=False, hash=False)

    def git_remote(self) -> Optional[str]:
        if "remote" not in self._cache:
            self._cache["remote"] = _git(
                self.project_root, "config", "--get", "remote.origin.url")
        return self._cache["remote"]

    def git_branch(self) -> Optional[str]:
        if "branch" not in self._cache:
            # symbolic-ref works in a repo with no commits yet; rev-parse
            # covers a detached HEAD (yields "HEAD").
            self._cache["branch"] = _git(
                self.project_root, "symbolic-ref", "-q", "--short", "HEAD") or \
                _git(self.project_root, "rev-parse", "--abbrev-ref", "HEAD")
        return self._cache["branch"]

    def git_org(self) -> Optional[str]:
        return parse_git_org_repo(self.git_remote())[0]

    def git_repo(self) -> Optional[str]:
        return parse_git_org_repo(self.git_remote())[1]

    def git_queried(self) -> bool:
        """True if any git fact has been looked up (for tests/diagnostics)."""
        return bool(self._cache)


class SiteConfig:
    """Base class for site-config plugins. Override the hooks you need."""

    def get_store(self, ctx: StoreContext) -> Optional[str]:
        """Return a store root path, "" / "local" for no store, or None to
        defer (no opinion)."""
        return None


def _load_entry_points() -> List[Any]:
    from importlib.metadata import entry_points
    try:
        return list(entry_points(group=ENTRY_POINT_GROUP))
    except TypeError:  # pragma: no cover - very old importlib.metadata
        return list(entry_points().get(ENTRY_POINT_GROUP, []))


class SiteConfigRgy:
    """Registry of available site configs and selection of the active one."""

    _inst: Optional["SiteConfigRgy"] = None

    def __init__(self):
        self._configs: List[Tuple[str, Any]] = []
        self._errors: List[Tuple[str, str]] = []
        self._loaded = False
        self._active: Optional[SiteConfig] = None
        self._active_name: Optional[str] = None
        self._active_reason: Optional[str] = None
        self._selected = False

    @classmethod
    def inst(cls) -> "SiteConfigRgy":
        if cls._inst is None:
            cls._inst = SiteConfigRgy()
        return cls._inst

    @classmethod
    def reset(cls):
        cls._inst = None

    def register(self, name: str, target: Any):
        self._configs.append((name, target))

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        for ep in _load_entry_points():
            try:
                self._configs.append((ep.name, ep.load()))
            except Exception as e:
                _log.warning("Failed to load site config '%s': %s", ep.name, e)
                self._errors.append((ep.name, str(e)))

    def names(self) -> List[str]:
        self._load()
        return [n for n, _ in self._configs]

    def errors(self) -> List[Tuple[str, str]]:
        self._load()
        return list(self._errors)

    def _instantiate(self, name: str, target: Any) -> Optional[SiteConfig]:
        try:
            obj = target()
        except Exception as e:
            _log.warning("Failed to instantiate site config '%s': %s", name, e)
            self._errors.append((name, str(e)))
            return None
        return obj

    def active(self, yaml_name: Optional[str] = None,
               yaml_src: Optional[str] = None) -> Optional[SiteConfig]:
        """Return the active site config. ``yaml_name`` is the ``site-config:``
        value from the user/site config file (``yaml_src`` names that file)."""
        if self._selected:
            return self._active
        self._selected = True
        self._load()
        if not self._configs:
            return None
        env_name = os.environ.get("DFM_SITE_CONFIG_NAME")
        pick: Optional[Tuple[str, Any]] = None
        reason = None
        for want, why in ((env_name, "env:DFM_SITE_CONFIG_NAME"),
                          (yaml_name, yaml_src or "config:site-config")):
            if want:
                for n, t in self._configs:
                    if n == want:
                        pick, reason = (n, t), why
                if pick is None:
                    _log.warning("Site config '%s' (from %s) is not installed; "
                                 "available: %s", want, why,
                                 ", ".join(self.names()) or "none")
                break
        if pick is None and not (env_name or yaml_name):
            pick, reason = self._configs[-1], "last-registered"
        if pick is None:
            return None
        self._active = self._instantiate(*pick)
        if self._active is not None:
            self._active_name = pick[0]
            self._active_reason = reason
        return self._active

    @property
    def active_name(self) -> Optional[str]:
        return self._active_name

    @property
    def active_reason(self) -> Optional[str]:
        return self._active_reason
