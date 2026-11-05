"""dfm show site-config: active site plugin, config files and store decision."""
import json
import os

from ...config_paths import (install_config_path, project_config_path,
                             site_config_path, user_config_paths)
from ...site_config import SiteConfigRgy
from ...store_config import resolve_store
from ...rundir_store import find_pkg_root, make_context, rundir_path


class CmdShowSiteConfig:
    """Show the active site configuration and the files it is read from."""

    def __call__(self, args):
        pkg_root = find_pkg_root(args)
        files = []
        for layer, path in (("install", install_config_path()),
                            ("site", site_config_path())):
            files.append((layer, path))
        for p in user_config_paths():
            files.append(("user", p))
        if pkg_root is not None:
            files.append(("project", project_config_path(pkg_root)))

        ctx = None
        if pkg_root is not None:
            from ..store.common import project_package
            ctx = make_context(rundir_path(pkg_root), pkg_root,
                               project_package(pkg_root))
        d = resolve_store(ctx, pkg_root, full=True)
        rgy = SiteConfigRgy.inst()
        data = {
            "plugins": rgy.names(),
            "plugin_errors": [{"name": n, "error": e} for n, e in rgy.errors()],
            "active_plugin": rgy.active_name,
            "active_plugin_reason": rgy.active_reason,
            "files": [{"layer": l, "path": p,
                       "exists": bool(p and os.path.isfile(p))} for l, p in files],
            "project_root": pkg_root,
            "store": {"root": d.root, "provenance": d.provenance,
                      "chain": [{"source": s, "value": v} for s, v in d.chain]},
        }
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
            return 0
        print("Site config plugins: %s" % (", ".join(data["plugins"]) or "(none installed)"))
        if rgy.active_name:
            print("  active:  %s (%s)" % (rgy.active_name, rgy.active_reason))
        for n, e in rgy.errors():
            print("  error:   %s: %s" % (n, e))
        print("Config files:")
        for f in data["files"]:
            print("  %-8s %s%s" % (f["layer"], f["path"] or "-",
                                   "" if f["exists"] else "  (not present)"))
        print("Rundir store: %s (from %s)" % (d.root or "local", d.provenance))
        for s, v in d.chain:
            print("  %s %-50s %s" % ("*" if s == d.provenance else " ", s, v))
        return 0
