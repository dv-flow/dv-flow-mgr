import datetime
import sys

from rich.text import Text

from ...rundir_store import RundirError
from ...rundir_store_entry import is_store_root
from ...rundir_store_ops import (SIZES_CACHED, SIZES_MEASURE, execute_gc,
                                 fmt_size, fs_usage, parse_duration,
                                 parse_size, plan_gc, read_selection,
                                 store_lock)
from .common import confirm, entry_filter, sizes_mode, store_root_for
from .render import compact_table, console, json_doc


class CmdStoreGc:
    """dfm store gc"""

    def __call__(self, args):
        root = store_root_for(args)
        if not is_store_root(root):
            raise RundirError("%s is not a rundir store (no .dfm-store.yaml); "
                              "refusing to delete anything. Use 'dfm store "
                              "init' if it really is one." % root)
        try:
            older = parse_duration(args.older_than) if args.older_than else None
            reclaim = parse_size(args.reclaim) if args.reclaim else None
            target_free = parse_size(args.target_free) if args.target_free else None
        except ValueError as e:
            raise RundirError(str(e))
        selection = None
        if args.from_file or args.entries:
            selection = list(args.entries or [])
            if args.from_file:
                if args.from_file == "-":
                    text = sys.stdin.read()
                else:
                    try:
                        with open(args.from_file) as fp:
                            text = fp.read()
                    except OSError as e:
                        raise RundirError("Cannot read %s: %s" % (args.from_file, e))
                selection += read_selection(text)
            if not selection:
                raise RundirError("The selection is empty; nothing to do")
        flt = entry_filter(args)
        flt.older_than = None      # --older-than is a gc criterion, not a filter
        lk = store_lock(root)
        if not lk.acquire(blocking=False):
            raise RundirError("Another 'dfm store gc' is running on %s" % root)
        try:
            plan = plan_gc(root, flt, orphans=args.orphans, older_than=older,
                           include_unknown=args.include_unknown, force=args.force,
                           selection=selection, reclaim=reclaim,
                           target_free=target_free,
                           sizes=sizes_mode(args, SIZES_MEASURE))
            now = datetime.datetime.now(datetime.timezone.utc)
            total = plan.size
            fs = fs_usage(root)
            out = None
            if args.json:
                out = {"store": root, "dry_run": args.dry_run, "need": plan.need,
                       "size": total, "filesystem": fs, "errors": plan.errors,
                       "delete": [dict(c.rec.to_dict(now), reason=c.reason)
                                  for c in plan.delete],
                       "skipped": [dict(c.rec.to_dict(now), reason=c.reason)
                                   for c in plan.skipped]}
            else:
                con = console()
                if plan.need is not None:
                    con.print("To reclaim: [bold]%s[/bold]" % fmt_size(plan.need))
                if plan.delete:
                    con.print(compact_table(
                        [(c.rec, c.rec.status.value, c.reason) for c in plan.delete],
                        now, title="To delete from %s" % root, label="STATUS"))
                if plan.skipped:
                    con.print(compact_table(
                        [(c.rec, c.rec.status.value, c.reason) for c in plan.skipped],
                        now, title="Skipped", label="STATUS"))
                for e in plan.errors:
                    con.print("[yellow]%s[/yellow]" % e)
                t = Text()
                t.append("%d entr%s to delete, %s" % (
                    len(plan.delete), "y" if len(plan.delete) == 1 else "ies",
                    fmt_size(total)), style="bold")
                if fs and fs.get("total"):
                    t.append("  ·  free after: %s of %s (now %s)" % (
                        fmt_size(fs["free"] + total), fmt_size(fs["total"]),
                        fmt_size(fs["free"])))
                con.print(t)
            if args.dry_run or not plan.delete:
                if out is not None:
                    print(json_doc("store.gc", **out))
                return 1 if (selection is not None and plan.errors) else 0
            if not args.yes:
                if not sys.stdin.isatty() or args.from_file == "-":
                    raise RundirError("Not a terminal; pass -y to delete without "
                                      "confirmation")
                if not confirm("Delete %d entries (%s)?" % (len(plan.delete),
                                                           fmt_size(total))):
                    print("Aborted")
                    return 1
            removed, failed = execute_gc(root, plan)
            freed = sum(c.rec.size or 0 for c in removed)
            if out is not None:
                out["removed"] = [c.rec.name for c in removed]
                out["freed"] = freed
                out["failed"] = [{"name": c.rec.name, "error": e} for c, e in failed]
                print(json_doc("store.gc", **out))
            else:
                for c, e in failed:
                    print("  failed  %s: %s" % (c.rec.name, e), file=sys.stderr)
                console().print("[green]Removed %d entr%s, freed %s[/green]" % (
                    len(removed), "y" if len(removed) == 1 else "ies",
                    fmt_size(freed)))
            return 1 if failed else 0
        finally:
            lk.release()
