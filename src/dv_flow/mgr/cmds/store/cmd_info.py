import json
import os

from ...rundir_store import inspect_rundir, rundir_path
from ...rundir_store_entry import is_store_root
from .common import project_decision, project_root

_STATE_DESC = {
    "none": "does not exist yet",
    "local": "local directory",
    "ok": "linked to a store entry",
    "unmanaged-symlink": "symlink to a directory outside any store",
    "copied": "shares its entry with another project (copied?); the next run forks it",
    "moved": "entry belongs to a previous project location; the next run adopts it",
    "dangling": "symlink target is missing",
    "file": "not a directory",
}


class CmdStoreInfo:
    """dfm store info"""

    def __call__(self, args):
        pkg_root = project_root(args)
        d, ctx = project_decision(args, pkg_root, full=True)
        link = rundir_path(pkg_root)
        info = inspect_rundir(link)
        mismatch = False
        if info.entry is not None and info.state not in ("dangling", "file"):
            here = os.path.realpath(os.path.dirname(info.entry))
            want = os.path.realpath(d.root) if d.is_store else None
            mismatch = info.meta is not None and here != want
        stats = None
        if getattr(args, "size", False) and info.entry and os.path.isdir(info.entry):
            from ...rundir_store_entry import measure, write_stats
            stats = measure(info.entry)
            if info.meta is not None:
                write_stats(info.entry, stats)
        elif info.state == "local" and getattr(args, "size", False):
            from ...rundir_store_entry import measure
            stats = measure(link)
        data = {
            "store": d.root,
            "provenance": d.provenance,
            "create": d.create,
            "chain": [{"source": s, "value": v} for s, v in d.chain],
            "store_initialized": bool(d.root and is_store_root(d.root)),
            "project_root": pkg_root,
            "rundir": link,
            "state": info.state,
            "target": info.entry,
            "mismatch": mismatch,
            "meta": info.meta.to_dict() if info.meta else None,
            "stats": stats.to_dict() if stats else None,
        }
        if getattr(args, "json", False):
            from .render import json_doc
            print(json_doc("store.info", **data))
            return 0
        print("Store:     %s" % (d.root or "(none -- local rundir)"))
        print("  from:    %s" % d.provenance)
        if d.root:
            print("  exists:  %s%s" % (
                "yes" if os.path.isdir(d.root) else "no",
                "" if data["store_initialized"] or not os.path.isdir(d.root)
                else " (no .dfm-store.yaml marker)"))
        print("Layers consulted:")
        for s, v in d.chain:
            mark = "*" if s == d.provenance else " "
            print("  %s %-50s %s" % (mark, s, v))
        print("Project:   %s" % pkg_root)
        print("Rundir:    %s" % link)
        print("  state:   %s (%s)" % (info.state, _STATE_DESC.get(info.state, "")))
        if info.entry:
            print("  target:  %s" % info.entry)
        if info.meta is not None:
            m = info.meta
            print("  entry:   created %s, last used %s, by %s@%s, source %s" % (
                m.created, m.last_used, m.user, m.host, m.store_source))
        if stats is not None:
            from ...rundir_store_ops import fmt_size
            from .render import bar, console
            from rich.table import Table
            from rich import box
            con = console()
            con.print("  size:    [bold]%s[/bold] on disk (%s apparent), %d files" % (
                fmt_size(stats.disk), fmt_size(stats.apparent), stats.files))
            if stats.top:
                t = Table(box=box.SIMPLE_HEAD, title="  Largest top-level directories",
                          title_justify="left", pad_edge=False)
                t.add_column("NAME")
                t.add_column("SIZE", justify="right")
                t.add_column("", no_wrap=True)
                for n, v in stats.top:
                    t.add_row(n, fmt_size(v), bar(v / stats.disk if stats.disk else 0, 24))
                con.print(t)
        if mismatch:
            print("  note:    the rundir is not in the configured store; run "
                  "'dfm store relink' to move it")
        if info.state == "local" and d.is_store:
            print("  note:    run 'dfm store migrate' to move it into the store")
        return 0
