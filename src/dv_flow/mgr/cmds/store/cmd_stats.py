import datetime
import sys

from rich.columns import Columns
from rich.text import Text

from ...rundir_store_entry import is_store_root
from ...rundir_store_ops import (DEFAULT_STALE, SIZES_MEASURE, aggregate,
                                 find_candidates, fmt_age, fmt_size,
                                 list_entries, parse_duration)
from .common import entry_filter, scope_flags, sizes_mode, store_root_for
from .render import (actions_panel, console, entries_table, fs_panel,
                     grouped_table, json_doc)


class CmdStoreStats:
    """dfm store stats: where the space goes, and what can be reclaimed."""

    def __call__(self, args):
        root = store_root_for(args)
        if not is_store_root(root):
            print("Warning: %s has no .dfm-store.yaml marker" % root, file=sys.stderr)
        now = datetime.datetime.now(datetime.timezone.utc)
        stale = parse_duration(args.stale) if args.stale else DEFAULT_STALE
        recs = list_entries(root, entry_filter(args),
                            sizes=sizes_mode(args, SIZES_MEASURE), now=now)
        cands = find_candidates(recs, stale_secs=stale, now=now)
        data = aggregate(recs, root, cands, top=args.top, now=now)
        if args.json:
            by_name = {r.name: r for r in recs}
            data["largest"] = [by_name[n].to_dict(now) for n in data["largest"]]
            print(json_doc("store.stats", stale_after_s=int(stale), **data))
            return 0

        c = console()
        total = data["size"]
        c.print(fs_panel(root, data["filesystem"], total))
        head = Text()
        head.append("%d entries" % data["entries"], style="bold")
        head.append("  ·  %s" % fmt_size(total), style="bold magenta")
        head.append("  ·  %d user%s" % (data["users"], "" if data["users"] == 1 else "s"))
        if data["sized"] < data["entries"]:
            head.append("  ·  %d not measured" % (data["entries"] - data["sized"]),
                        style="yellow")
        if data["stale_sizes"]:
            head.append("  ·  %d sizes stale" % data["stale_sizes"], style="dim")
        c.print(head)
        if not recs:
            return 0
        c.print(Columns([
            grouped_table("By status", data["by_status"], total, "STATUS",
                          style_by_key=True, width=16),
            grouped_table("By last use", [e for e in data["by_last_used"]],
                          total, "LAST USED", width=16),
        ], padding=(0, 4)))
        top = [r for n in data["largest"] for r in recs if r.name == n]
        c.print(entries_table(top, now, title="Largest %d entries" % len(top)))
        c.print(grouped_table("By project", data["by_project"], total,
                              "PROJECT (git org/repo or package)", limit=args.top))
        if data["users"] > 1:
            c.print(grouped_table("By user", data["by_user"], total, "USER",
                                  limit=args.top))
        if len(data["by_host"]) > 1:
            c.print(grouped_table("By host (last used on)", data["by_host"], total,
                                  "HOST", limit=args.top))

        rec_tiers = {t["tier"]: t for t in data.get("reclaimable", [])}
        line = Text("Reclaimable: ", style="bold")
        safe = rec_tiers.get("safe", {"count": 0, "size": 0})
        review = rec_tiers.get("review", {"count": 0, "size": 0})
        line.append("%s safe" % fmt_size(safe["size"]), style="bold red")
        line.append(" (%d orphaned/retargeted)" % safe["count"])
        line.append("  ·  ")
        line.append("%s to review" % fmt_size(review["size"]), style="bold yellow")
        line.append(" (%d unverifiable or unused > %s)" % (review["count"], fmt_age(stale)))
        c.print(line)
        sf = scope_flags(args)
        acts = []
        if safe["count"]:
            acts.append(("delete entries whose project is gone (%s)" % fmt_size(safe["size"]),
                         "dfm store gc%s -y" % sf))
        if review["count"]:
            acts.append(("see the entries to review, biggest first",
                         "dfm store candidates%s --tier review" % sf))
        if data["sized"] < data["entries"] or data["stale_sizes"]:
            acts.append(("re-measure sizes", "dfm store stats%s --refresh" % sf))
        p = actions_panel(acts)
        if p is not None:
            c.print(p)
        return 0
