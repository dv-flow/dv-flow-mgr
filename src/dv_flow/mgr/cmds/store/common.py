"""Helpers shared by the `dfm store` subcommands."""
import os
import sys
from typing import Optional, Tuple

from ...rundir_store import RundirError, find_pkg_root, make_context, rundir_path
from ...store_config import StoreDecision, resolve_store


def project_root(args, required: bool = True) -> Optional[str]:
    root = find_pkg_root(args)
    if root is None and required:
        raise RundirError("No flow.yaml defining a package was found in %s or "
                          "its parent directories" % os.getcwd())
    return root


def project_package(pkg_root: str) -> Optional[str]:
    """The package name from the root flow file, without loading it."""
    from ...util.util import find_root_flow_file, _classify_flow_file
    f = find_root_flow_file(pkg_root)
    if f is None:
        return None
    try:
        if f.endswith(".toml"):
            import tomllib
            with open(f, "rb") as fp:
                doc = tomllib.load(fp)
        else:
            import yaml
            with open(f) as fp:
                doc = yaml.safe_load(fp)
        pkg = doc.get("package") if isinstance(doc, dict) else None
        if isinstance(pkg, dict):
            return pkg.get("name")
        return pkg if isinstance(pkg, str) else None
    except Exception:
        return None


def project_decision(args, pkg_root: str, full: bool = False
                     ) -> Tuple[StoreDecision, object]:
    link = rundir_path(pkg_root)
    ctx = make_context(link, pkg_root, project_package(pkg_root))
    d = resolve_store(ctx, pkg_root,
                      cli_store=getattr(args, "store", None),
                      cli_no_store=bool(getattr(args, "no_store", False)),
                      full=full)
    return d, ctx


def store_root_for(args) -> str:
    """The store to operate on: --store DIR, else the configured store for
    the current project (if any), else the configured store with no project
    context."""
    if getattr(args, "store", None):
        return os.path.abspath(os.path.expanduser(args.store))
    pkg_root = find_pkg_root(args) if hasattr(args, "root") else find_pkg_root(None)
    if pkg_root is not None:
        d, _ = project_decision(args, pkg_root)
    else:
        d = resolve_store(None, None)
    if not d.is_store:
        raise RundirError("No rundir store is configured; pass --store DIR "
                          "or set DFM_STORE")
    return d.root


def confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        ans = input("%s [y/N] " % prompt)
    except EOFError:
        return False
    return ans.strip().lower() in ("y", "yes")


def entry_filter(args):
    """EntryFilter from the common selection options."""
    from ...rundir_store_ops import EntryFilter, parse_duration, parse_size
    older = getattr(args, "older_than", None)
    larger = getattr(args, "larger_than", None)
    try:
        return EntryFilter(
            user=getattr(args, "user", None),
            all_users=bool(getattr(args, "all_users", False)),
            statuses=list(getattr(args, "status", None) or []),
            older_than=parse_duration(older) if older else None,
            larger_than=parse_size(larger) if larger else None,
            package=getattr(args, "package", None),
            host=getattr(args, "host", None))
    except ValueError as e:
        raise RundirError(str(e))


def sizes_mode(args, default):
    from ...rundir_store_ops import (SIZES_CACHED, SIZES_MEASURE,
                                     SIZES_REFRESH)
    if getattr(args, "refresh", False):
        return SIZES_REFRESH
    if getattr(args, "size", False):
        return SIZES_MEASURE
    if getattr(args, "no_measure", False):
        return SIZES_CACHED
    return default


def scope_flags(args) -> str:
    """The selection flags to repeat in suggested commands."""
    out = []
    if getattr(args, "store", None):
        out.append("--store %s" % args.store)
    if getattr(args, "all_users", False):
        out.append("--all-users")
    elif getattr(args, "user", None):
        out.append("--user %s" % args.user)
    return (" " + " ".join(out)) if out else ""
