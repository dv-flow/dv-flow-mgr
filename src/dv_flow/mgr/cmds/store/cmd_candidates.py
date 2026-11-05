import datetime
import sys

from rich.text import Text

from ...rundir_store_entry import is_store_root
from ...rundir_store_ops import (DEFAULT_STALE, SIZES_MEASURE, find_candidates,
                                 fmt_age, fmt_size, list_entries,
                                 parse_duration)
from .common import entry_filter, scope_flags, sizes_mode, store_root_for
from .render import actions_panel, candidates_table, console, json_doc


class CmdStoreCandidates:
    """dfm store candidates: a ranked list of entries to clean up."""

    def __call__(self, args):
        root = store_root_for(args)
        if not is_store_root(root):
            print("Warning: %s has no .dfm-store.yaml marker" % root, file=sys.stderr)
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = parse_duration(args.stale) if args.stale else DEFAULT_STALE
        recs = list_entries(root, entry_filter(args),
                            sizes=sizes_mode(args, SIZES_MEASURE), now=now)
        cands = find_candidates(recs, stale_secs=stale, force=args.force, now=now)
        if args.tier:
            cands = [c for c in cands if c.tier in args.tier]
        if args.limit:
            cands = cands[:args.limit]

        if args.json:
            tiers = {}
            for c in cands:
                t = tiers.setdefault(c.tier, {"count": 0, "size": 0})
                t["count"] += 1
                t["size"] += c.rec.size or 0
            print(json_doc("store.candidates", store=root, stale_after_s=int(stale),
                           totals=tiers, candidates=[c.to_dict(now) for c in cands]))
            return 0
        if args.format in ("names", "links", "paths"):
            for c in cands:
                r = c.rec
                v = {"names": r.name, "paths": r.path,
                     "links": r.meta.link if r.meta else None}[args.format]
                if v:
                    print("%s\t# %s %s %s" % (v, c.tier, fmt_size(r.size), c.reason)
                          if args.annotate else v)
            return 0

        con = console()
        if not cands:
            con.print("[green]Nothing to clean up in %s.[/green]" % root)
            return 0
        tbl = candidates_table(cands, now, title="Cleanup candidates in %s" % root)
        con.print(tbl)
        safe = [c for c in cands if c.tier == "safe"]
        review = [c for c in cands if c.tier == "review"]
        tot = Text()
        tot.append("%d safe (%s)" % (len(safe), fmt_size(sum(c.rec.size or 0 for c in safe))),
                   style="bold red")
        tot.append("  ·  ")
        tot.append("%d to review (%s)" % (len(review),
                                         fmt_size(sum(c.rec.size or 0 for c in review))),
                   style="bold yellow")
        con.print(tot)
        sf = scope_flags(args)
        acts = []
        if safe:
            acts.append(("delete the safe ones (project gone)", "dfm store gc%s -y" % sf))
        if review:
            acts.append(("review, edit, then delete a chosen list",
                         "dfm store candidates%s --tier review --format names "
                         "--annotate > cleanup.txt\n"
                         "dfm store gc%s --from cleanup.txt -y" % (sf, sf)))
        acts.append(("free a fixed amount, oldest first (dry run)",
                     "dfm store gc%s --reclaim 100G --dry-run" % sf))
        con.print(actions_panel(acts))
        return 0
