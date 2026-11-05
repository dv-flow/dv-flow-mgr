import datetime
import sys

from ...rundir_store_entry import is_store_root
from ...rundir_store_ops import SIZES_CACHED, age_secs, fmt_size, list_entries
from .common import entry_filter, sizes_mode, store_root_for
from .render import console, entries_table, entry_cards, json_doc


class CmdStoreList:
    """dfm store list"""

    def __call__(self, args):
        root = store_root_for(args)
        if not is_store_root(root):
            print("Warning: %s has no .dfm-store.yaml marker" % root, file=sys.stderr)
        now = datetime.datetime.now(datetime.timezone.utc)
        mode = sizes_mode(args, SIZES_CACHED)
        if args.sort == "size" and mode == SIZES_CACHED:
            from ...rundir_store_ops import SIZES_MEASURE
            mode = SIZES_MEASURE
        recs = list_entries(root, entry_filter(args), sizes=mode, now=now)
        key = {
            "name": lambda r: r.name,
            "size": lambda r: -(r.size or 0),
            "last-used": lambda r: -(age_secs(r.meta, now) or 0),
            "age": lambda r: -(age_secs(r.meta, now) or 0),
            "created": lambda r: (r.meta.created or "") if r.meta else "",
        }[args.sort]
        recs.sort(key=key)
        total = len(recs)
        if args.limit:
            recs = recs[:args.limit]
        fmt = getattr(args, "format", None)
        if args.json:
            print(json_doc("store.list", store=root, total_entries=total,
                           entries=[r.to_dict(now) for r in recs]))
            return 0
        if fmt in ("names", "links", "paths"):
            for r in recs:
                v = {"names": r.name, "paths": r.path,
                     "links": r.meta.link if r.meta else None}[fmt]
                if v:
                    print(v)
            return 0
        c = console()
        size = sum(r.size or 0 for r in recs)
        title = "Store %s — %d entr%s%s" % (
            root, total, "y" if total == 1 else "ies",
            (", %s" % fmt_size(size)) if any(r.size is not None for r in recs) else "")
        if args.limit and total > len(recs):
            title += " (showing %d)" % len(recs)
        if not recs:
            c.print(title)
            return 0
        if args.long:
            c.print(title, style="bold")
            c.print(entry_cards(recs, now))
        else:
            c.print(entries_table(recs, now, title=title))
        if any(r.stats_stale for r in recs if r.stats):
            c.print("[dim]~ size measured before the last use; --size re-measures[/dim]")
        elif not any(r.size is not None for r in recs):
            c.print("[dim]Sizes not measured yet; use --size (or 'dfm store stats')[/dim]")
        return 0
