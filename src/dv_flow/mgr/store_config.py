"""Resolve where a project's rundir lives: a rundir store root, or local.

Resolution order (first layer with an opinion wins; see
RUNDIR_STORE_DESIGN.md §5.3):

1. CLI: ``--no-store`` / ``--store DIR``
2. ``DFM_STORE`` env var ("" or "local" means no store)
3. Project ``.dfm/config.yaml``: may only opt out (``store: {root: local}``)
4. User config, 5. site config, 6. install config. In each file the
   ``store.rules`` list is evaluated (first match) before ``store.root``.
7. The active Python :class:`~dv_flow.mgr.site_config.SiteConfig` plugin
8. Default: local ``<pkg_root>/rundir``
"""
import dataclasses as dc
import fnmatch
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import config_paths
from .site_config import SiteConfigRgy, StoreContext

_log = logging.getLogger("StoreConfig")

LOCAL_VALUES = ("", "local")

MATCH_KEYS = ("path", "link", "user", "host", "git-remote", "git-branch",
              "package", "env")


@dc.dataclass
class StoreDecision:
    """The resolved store. ``root`` is None for a local rundir."""
    root: Optional[str] = None
    create: bool = True
    provenance: str = "default:local"
    # Every layer consulted and what it said: (source, answer)
    chain: List[Tuple[str, str]] = dc.field(default_factory=list)

    @property
    def is_store(self) -> bool:
        return self.root is not None


class _Unresolved(Exception):
    pass


_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_root(value: str, ctx: Optional[StoreContext]) -> str:
    """Expand ``${user}``, ``${host}``, ``${package}``, ``${git_org}``,
    ``${git_repo}``, then ``${ENV_VAR}``, then ``~``. Raises _Unresolved if a
    variable has no value."""
    def _sub(m):
        name = m.group(1)
        val = None
        if ctx is not None:
            if name == "user":
                val = ctx.user
            elif name == "host":
                val = ctx.host
            elif name == "package":
                val = ctx.package
            elif name == "git_org":
                val = ctx.git_org()
            elif name == "git_repo":
                val = ctx.git_repo()
        if val is None:
            val = os.environ.get(name)
        if val is None or val == "":
            raise _Unresolved(name)
        return str(val)
    return os.path.expanduser(_VAR_RE.sub(_sub, value))


def _ctx_value(key: str, ctx: StoreContext) -> Optional[str]:
    if key == "path":
        return ctx.project_root
    if key == "link":
        return ctx.link
    if key == "user":
        return ctx.user
    if key == "host":
        return ctx.host
    if key == "package":
        return ctx.package
    if key == "git-remote":
        return ctx.git_remote()
    if key == "git-branch":
        return ctx.git_branch()
    return None


def rule_matches(rule: Dict[str, Any], ctx: StoreContext, src: str) -> bool:
    """All keys of ``rule['match']`` must match (fnmatch; ``*`` also matches
    across ``/``). Git keys are only looked up when present."""
    match = rule.get("match") or {}
    if not isinstance(match, dict):
        _log.warning("%s: rule '%s' has a non-mapping 'match'; ignored",
                     src, rule.get("name", "?"))
        return False
    for key, pat in match.items():
        if key not in MATCH_KEYS:
            _log.warning("%s: rule '%s' has unknown match key '%s'; rule ignored",
                         src, rule.get("name", "?"), key)
            return False
        if key == "env":
            if not isinstance(pat, dict):
                _log.warning("%s: rule '%s': 'env' must be a mapping",
                             src, rule.get("name", "?"))
                return False
            for var, vpat in pat.items():
                val = os.environ.get(var)
                if val is None or not fnmatch.fnmatchcase(val, str(vpat)):
                    return False
            continue
        val = _ctx_value(key, ctx)
        if val is None or not fnmatch.fnmatchcase(val, str(pat)):
            return False
    return True


def _normalize(value: Any, ctx: Optional[StoreContext], src: str
               ) -> Tuple[bool, Optional[str]]:
    """Return (ok, root). root None means local. ok False means the value
    could not be used (warned) and the layer should be treated as silent."""
    if value is None:
        return False, None
    value = str(value)
    if value.strip() in LOCAL_VALUES:
        return True, None
    try:
        root = expand_root(value, ctx)
    except _Unresolved as e:
        _log.warning("%s: store root '%s' uses ${%s}, which has no value; ignored",
                     src, value, e.args[0])
        return False, None
    if not os.path.isabs(root):
        _log.warning("%s: store root '%s' is not an absolute path; ignored",
                     src, value)
        return False, None
    return True, os.path.normpath(root)


def _describe(root: Optional[str]) -> str:
    return "local" if root is None else root


def _eval_file_layer(layer: str, path: Optional[str], data: Dict[str, Any],
                     ctx: Optional[StoreContext]
                     ) -> Optional[Tuple[Optional[str], str, bool]]:
    """Evaluate one user/site/install file. Returns (root, provenance, create)
    or None if the file has no opinion."""
    sect = data.get("store")
    if sect is None:
        return None
    if not isinstance(sect, dict):
        _log.warning("%s config %s: 'store' must be a mapping; ignored", layer, path)
        return None
    create = bool(sect.get("create", True))
    rules = sect.get("rules") or []
    if not isinstance(rules, list):
        _log.warning("%s config %s: 'store.rules' must be a list; ignored", layer, path)
        rules = []
    if rules and ctx is not None:
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            name = rule.get("name", "#%d" % i)
            src = "%s-rule:%s" % (layer, name)
            if "root" not in rule:
                _log.warning("%s config %s: rule '%s' has no 'root'; ignored",
                             layer, path, name)
                continue
            if rule_matches(rule, ctx, "%s config %s" % (layer, path)):
                ok, root = _normalize(rule["root"], ctx, src)
                if ok:
                    return root, src, create
    if "root" in sect:
        src = "%s-config:%s" % (layer, path)
        ok, root = _normalize(sect["root"], ctx, src)
        if ok:
            return root, src, create
    return None


def _eval_project_layer(path: Optional[str], data: Dict[str, Any]
                        ) -> Optional[str]:
    """Project files may only opt out. Returns a provenance string if the
    project opts out, else None."""
    sect = data.get("store")
    if sect is None:
        return None
    if not isinstance(sect, dict):
        _log.warning("project config %s: 'store' must be a mapping; ignored", path)
        return None
    if sect.get("rules"):
        _log.warning("project config %s: 'store.rules' is not allowed in a "
                     "project file; ignored (store locations are a user/site "
                     "setting)", path)
    if "root" in sect:
        v = sect["root"]
        if v is not None and str(v).strip() in LOCAL_VALUES:
            return "project-config:%s" % path
        _log.warning("project config %s: 'store.root: %s' ignored -- a project "
                     "may only set 'root: local'", path, v)
    return None


def site_config_name(layers) -> Tuple[Optional[str], Optional[str]]:
    """The ``site-config:`` selection from the user, then site, file."""
    for layer, path, data in reversed(layers):
        if layer in ("user", "site") and data.get("site-config"):
            return str(data["site-config"]), "%s-config:%s" % (layer, path)
    return None, None


def resolve_store(ctx: Optional[StoreContext],
                  project_root: Optional[str] = None,
                  cli_store: Optional[str] = None,
                  cli_no_store: bool = False,
                  full: bool = False,
                  use_plugin: bool = True) -> StoreDecision:
    """Resolve the store for a project.

    ``ctx`` may be None when no project is known (e.g. ``dfm store list``);
    rules then never match. With ``full``, every layer is evaluated and
    recorded in ``chain`` even after a decision is made (for diagnostics).
    """
    if project_root is None and ctx is not None:
        project_root = ctx.project_root
    ret = StoreDecision()
    decided = False

    def _decide(root, prov, create=True):
        nonlocal decided
        ret.chain.append((prov, _describe(root)))
        if not decided:
            decided = True
            ret.root, ret.provenance, ret.create = root, prov, create

    # 1. CLI
    if cli_no_store:
        _decide(None, "cli:--no-store")
    elif cli_store is not None:
        ok, root = _normalize(cli_store, ctx, "cli:--store")
        if ok:
            _decide(root, "cli:--store")
        elif not os.path.isabs(os.path.expanduser(str(cli_store))):
            # A relative CLI path is unambiguous: relative to cwd.
            _decide(os.path.abspath(os.path.expanduser(str(cli_store))),
                    "cli:--store")
    if decided and not full:
        return ret

    # 2. Env
    if "DFM_STORE" in os.environ:
        ok, root = _normalize(os.environ["DFM_STORE"], ctx, "env:DFM_STORE")
        if ok:
            _decide(root, "env:DFM_STORE")
    if decided and not full:
        return ret

    layers = config_paths.config_layers(project_root)

    # 3. Project opt-out
    for layer, path, data in layers:
        if layer == "project" and project_root is not None:
            prov = _eval_project_layer(path, data)
            if prov is not None:
                _decide(None, prov)
    if decided and not full:
        return ret

    # 4-6. User, site, install (highest priority first)
    for layer, path, data in reversed(layers):
        if layer == "project":
            continue
        r = _eval_file_layer(layer, path, data, ctx)
        if r is not None:
            _decide(r[0], r[1], r[2])
            if not full:
                return ret

    # 7. Python site-config plugin
    if use_plugin and ctx is not None and (full or not decided):
        name, name_src = site_config_name(layers)
        rgy = SiteConfigRgy.inst()
        sc = rgy.active(name, name_src)
        if sc is not None:
            prov = "site-plugin:%s" % rgy.active_name
            try:
                val = sc.get_store(ctx)
            except Exception as e:
                _log.warning("Site config '%s' get_store() failed: %s",
                             rgy.active_name, e)
                val = None
            if val is not None:
                ok, root = _normalize(val, ctx, prov)
                if ok:
                    _decide(root, prov)

    # 8. Default
    if not decided:
        ret.chain.append(("default:local", "local"))
    return ret
