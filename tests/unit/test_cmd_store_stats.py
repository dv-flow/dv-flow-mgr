"""`dfm store` statistics and cleanup reporting: size measurement and
caching, aggregation, cleanup candidates, gc --reclaim/--target-free/--from,
and the human (Rich) and agent (JSON) output."""
import datetime
import json
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import rundir_store_ops as ops
from dv_flow.mgr.rundir_store_entry import (
    EntryMeta, measure, read_stats, stats_stale, write_marker, write_meta,
    write_stats)
from dv_flow.mgr.rundir_store_ops import (
    EntryFilter, SIZES_CACHED, SIZES_MEASURE, SIZES_REFRESH, aggregate,
    age_bucket, find_candidates, list_entries, parse_size, plan_gc,
    project_key, read_selection)
from dv_flow.mgr.site_config import current_host

HOST = current_host()
NOW = datetime.datetime.now(datetime.timezone.utc)
MB = 1 << 20


def iso(days):
    return (NOW - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mk(store, projs, name, mb, used_days, state="ok", pkg=None, remote=None,
        host=HOST, created_days=None, sessions=3):
    proj = projs / name
    link = proj / "rundir"
    e = store / ("_" + name)
    (e / "t.build").mkdir(parents=True)
    with open(e / "t.build" / "blob", "wb") as fp:
        fp.write(b"\0" * int(mb * MB))
    (e / "log").mkdir()
    (e / "log" / "l").write_bytes(b"x" * 1000)
    write_meta(str(e), EntryMeta(
        link=str(link), project_root=str(proj), package=pkg or name,
        user="me", uid=os.getuid(), host=host,
        git={"remote": remote, "branch": "main"} if remote else {},
        created=iso(created_days if created_days is not None else used_days + 10),
        last_used=iso(used_days), sessions=sessions))
    if state == "ok":
        proj.mkdir()
        os.symlink(e, link)
    elif state == "retargeted":
        link.mkdir(parents=True)
    return e


@pytest.fixture
def store(tmp_path):
    s = tmp_path / "store"
    s.mkdir()
    write_marker(str(s))
    p = tmp_path / "projs"
    p.mkdir()
    e = {
        "big": _mk(s, p, "big", 8, 2, remote="git@github.com:acme/soc.git"),
        "orphan": _mk(s, p, "orphan", 4, 60, state="orphan"),
        "stale": _mk(s, p, "stale", 2, 45, remote="https://github.com/acme/dma.git"),
        "retarget": _mk(s, p, "retarget", 1, 10, state="retargeted"),
        "fresh": _mk(s, p, "fresh", 1, 0.001),
        "remote": _mk(s, p, "remote", 3, 20, state="orphan", host="farm-07"),
    }
    # make 'remote' an unknown: its project dir is on another host
    from dv_flow.mgr.rundir_store_entry import read_meta
    m = read_meta(str(e["remote"]))
    m.link = "/hostlocal/remote/rundir"
    m.project_root = "/hostlocal/remote"
    write_meta(str(e["remote"]), m)
    return s, e


# ---------------------------------------------------------------- measure / cache

def test_measure_counts_hardlinks_once(tmp_path):
    e = tmp_path / "e"
    (e / "a").mkdir(parents=True)
    with open(e / "a" / "f", "wb") as fp:
        fp.write(b"\1" * MB)
    os.link(e / "a" / "f", e / "a" / "g")
    (e / ".dfm-rundir.json").write_text("{}")
    st = measure(str(e))
    assert st.files == 1 and st.apparent == MB
    assert st.top[0][0] == "a"
    assert st.last_modified and st.measured


def test_size_cache_and_staleness(store):
    s, e = store
    recs = list_entries(str(s), EntryFilter(), sizes=SIZES_CACHED)
    assert all(r.size is None for r in recs)
    recs = list_entries(str(s), EntryFilter(), sizes=SIZES_MEASURE)
    assert all(r.size is not None for r in recs)
    assert read_stats(str(e["big"])).disk >= 8 * MB
    # cached read now works without walking
    recs = list_entries(str(s), EntryFilter(), sizes=SIZES_CACHED)
    assert all(r.size is not None and not r.stats_stale for r in recs)
    # a later session makes the cached size stale
    from dv_flow.mgr.rundir_store_entry import read_meta, touch_meta
    import time
    time.sleep(1.1)
    touch_meta(str(e["big"]), read_meta(str(e["big"])))
    recs = {r.name: r for r in list_entries(str(s), EntryFilter(), sizes=SIZES_CACHED)}
    assert recs["_big"].stats_stale
    recs = {r.name: r for r in list_entries(str(s), EntryFilter(), sizes=SIZES_MEASURE)}
    assert not recs["_big"].stats_stale


def test_touch_counts_sessions(tmp_path):
    from dv_flow.mgr.rundir_store_entry import read_meta, touch_meta
    write_meta(str(tmp_path), EntryMeta(link="/x/rundir", project_root="/x", sessions=2))
    touch_meta(str(tmp_path), read_meta(str(tmp_path)))
    assert read_meta(str(tmp_path)).sessions == 3


# ---------------------------------------------------------------- filters

def test_filters(store):
    s, e = store
    names = lambda f: sorted(r.name for r in list_entries(str(s), f))
    assert names(EntryFilter(larger_than=parse_size("3M"))) == ["_big", "_orphan", "_remote"]
    assert names(EntryFilter(older_than=30 * 86400)) == ["_orphan", "_stale"]
    assert names(EntryFilter(package="re*")) == ["_remote", "_retarget"]
    assert names(EntryFilter(host="farm-*")) == ["_remote"]


@pytest.mark.parametrize("s,n", [("500M", 500 * MB), ("1.5G", int(1.5 * (1 << 30))),
                                 ("2GiB", 2 << 30), ("10", 10), ("1t", 1 << 40)])
def test_parse_size(s, n):
    assert parse_size(s) == n


def test_parse_size_bad():
    with pytest.raises(ValueError):
        parse_size("lots")


# ---------------------------------------------------------------- aggregate

def test_aggregate(store):
    s, e = store
    recs = list_entries(str(s), EntryFilter(), sizes=SIZES_MEASURE, this_host=HOST)
    cands = find_candidates(recs)
    d = aggregate(recs, str(s), cands, top=3)
    assert d["entries"] == 6 and d["sized"] == 6
    assert d["size"] == sum(r.size for r in recs)
    st = {g["key"]: g for g in d["by_status"]}
    assert st["ok"]["count"] == 3 and st["orphan"]["count"] == 1
    assert st["unknown"]["count"] == 1 and st["retargeted"]["count"] == 1
    ages = {g["key"]: g["count"] for g in d["by_last_used"]}
    assert ages == {"<1d": 1, "1-7d": 1, "7-30d": 2, "30-90d": 2, ">90d": 0}
    assert d["largest"][0] == "_big" and len(d["largest"]) == 3
    proj = {g["key"] for g in d["by_project"]}
    assert {"acme/soc", "acme/dma", "orphan"} <= proj
    assert d["filesystem"]["total"] > 0
    tiers = {t["tier"]: t for t in d["reclaimable"]}
    assert tiers["safe"]["count"] == 2 and tiers["review"]["count"] == 2


def test_age_bucket_and_project_key():
    assert age_bucket(10) == "<1d" and age_bucket(100 * 86400) == ">90d"
    assert age_bucket(None) == "unknown"
    assert project_key(EntryMeta(link="/a", project_root="/",
                                 git={"remote": "git@h:o/r.git"})) == "o/r"
    assert project_key(EntryMeta(link="/a", project_root="/", package="p")) == "p"


# ---------------------------------------------------------------- candidates

def test_candidates_tiers_and_order(store):
    s, e = store
    recs = list_entries(str(s), EntryFilter(), sizes=SIZES_MEASURE, this_host=HOST)
    cands = find_candidates(recs)
    kinds = {c.rec.name: (c.tier, c.kind) for c in cands}
    assert kinds == {"_orphan": ("safe", "orphan"),
                     "_retarget": ("safe", "retargeted"),
                     "_remote": ("review", "unknown"),
                     "_stale": ("review", "stale")}
    sizes = [c.rec.size for c in cands]
    assert sizes == sorted(sizes, reverse=True)        # biggest first
    # a shorter stale threshold pulls in the 2-day-old 'big' project
    names = {c.rec.name for c in find_candidates(recs, stale_secs=86400)}
    assert "_big" in names and "_fresh" not in names


# ---------------------------------------------------------------- gc extensions

def test_gc_reclaim_orphans_first_then_lru(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), reclaim=5 * MB, this_host=HOST)
    names = [c.rec.name for c in plan.delete]
    # orphan (4M) + retargeted (1M) are dead and go first; that is enough
    assert names[:2] == ["_orphan", "_retarget"] or set(names[:2]) == {"_orphan", "_retarget"}
    assert plan.size >= 5 * MB
    assert "_big" not in names and "_fresh" not in names


def test_gc_reclaim_shortfall_reported(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), orphans=True, reclaim=1 << 40, this_host=HOST)
    assert any("frees only" in m for m in plan.errors)


def test_gc_target_free_already_met(store, monkeypatch):
    s, e = store
    monkeypatch.setattr(ops, "fs_usage", lambda r: {"total": 100, "free": 90, "used": 10})
    plan = plan_gc(str(s), EntryFilter(), target_free=50, this_host=HOST)
    assert plan.delete == [] and plan.need == 0


def test_gc_target_free_computes_need(store, monkeypatch):
    s, e = store
    monkeypatch.setattr(ops, "fs_usage",
                        lambda r: {"total": 1 << 40, "free": 10 * MB, "used": 0})
    plan = plan_gc(str(s), EntryFilter(), target_free=13 * MB, this_host=HOST)
    assert plan.need == 3 * MB and plan.size >= 3 * MB


def test_gc_larger_than(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(larger_than=2 * MB), this_host=HOST)
    assert [c.rec.name for c in plan.delete] == ["_orphan"]


def test_gc_explicit_selection(store):
    s, e = store
    sel = read_selection("""
        # reviewed list
        _stale\t# review 2.0M stale
        %s
        /nope/rundir
        _fresh
    """ % (s.parent / "projs" / "big" / "rundir"))
    plan = plan_gc(str(s), EntryFilter(), selection=sel, this_host=HOST)
    assert sorted(c.rec.name for c in plan.delete) == ["_big", "_stale"]
    assert [c.rec.name for c in plan.skipped] == ["_fresh"]      # recent
    assert any("/nope/rundir" in m for m in plan.errors)
    plan = plan_gc(str(s), EntryFilter(), selection=["_fresh"], force=True, this_host=HOST)
    assert [c.rec.name for c in plan.delete] == ["_fresh"]


def test_gc_explicit_other_user_needs_all_users(store):
    s, e = store
    from dv_flow.mgr.rundir_store_entry import read_meta
    m = read_meta(str(e["stale"]))
    m.uid, m.user = os.getuid() + 1, "bob"
    write_meta(str(e["stale"]), m)
    plan = plan_gc(str(s), EntryFilter(), selection=["_stale"], this_host=HOST)
    assert plan.delete == [] and "another user" in plan.skipped[0].reason
    plan = plan_gc(str(s), EntryFilter(all_users=True), selection=["_stale"], this_host=HOST)
    assert [c.rec.name for c in plan.delete] == ["_stale"]


# ---------------------------------------------------------------- CLI

def _dfm(cwd, *args, stdin=None, columns="120"):
    env = dict(os.environ, COLUMNS=columns)
    return subprocess.run([sys.executable, "-m", "dv_flow.mgr", "store"] + list(args),
                          cwd=cwd, env=env, input=stdin, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=60)


def test_cli_stats_human(store):
    s, e = store
    r = _dfm(str(s.parent), "stats", "--store", str(s))
    assert r.returncode == 0, r.stderr
    for want in ("Filesystem", "By status", "By last use", "Largest",
                 "By project", "Reclaimable", "Suggested actions", "dfm store gc"):
        assert want in r.stdout, want
    assert "█" in r.stdout                                   # bar charts
    assert "\x1b[" not in r.stdout                           # no colour when piped


def test_cli_stats_json(store):
    s, e = store
    r = _dfm(str(s.parent), "stats", "--store", str(s), "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["schema"] == 1 and d["kind"] == "store.stats"
    assert d["entries"] == 6 and isinstance(d["size"], int)
    big = d["largest"][0]
    assert big["name"] == "_big" and big["size"] >= 8 * MB
    assert big["last_used_age_s"] > 0 and big["created"] and big["sessions"] == 3
    assert big["top"][0]["name"] == "t.build"


def test_cli_candidates_json_and_names_roundtrip(store):
    s, e = store
    r = _dfm(str(s.parent), "candidates", "--store", str(s), "--json")
    d = json.loads(r.stdout)
    assert d["kind"] == "store.candidates"
    assert {c["name"]: c["tier"] for c in d["candidates"]} == {
        "_orphan": "safe", "_retarget": "safe", "_remote": "review", "_stale": "review"}
    assert all(c["reason"] for c in d["candidates"])
    r = _dfm(str(s.parent), "candidates", "--store", str(s), "--tier", "review",
             "--format", "names", "--annotate")
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 2 and all("# review" in l for l in lines)
    r = _dfm(str(s.parent), "gc", "--store", str(s), "--from", "-", "-y",
             "--include-unknown", stdin=r.stdout)
    assert r.returncode == 0, r.stderr + r.stdout
    assert not os.path.exists(e["stale"]) and not os.path.exists(e["remote"])
    assert os.path.isdir(e["big"])


def test_cli_candidates_table(store):
    s, e = store
    r = _dfm(str(s.parent), "candidates", "--store", str(s))
    assert r.returncode == 0, r.stderr
    assert "project deleted" in r.stdout and "safe" in r.stdout and "review" in r.stdout


def test_cli_list_sort_limit_format(store):
    s, e = store
    r = _dfm(str(s.parent), "list", "--store", str(s), "--sort", "size",
             "--limit", "2", "--format", "names")
    assert r.stdout.split() == ["_big", "_orphan"]
    r = _dfm(str(s.parent), "list", "--store", str(s), "--sort", "last-used", "--json")
    d = json.loads(r.stdout)
    assert d["entries"][0]["name"] == "_orphan"                # longest unused
    r = _dfm(str(s.parent), "list", "--store", str(s), "--long", "--size")
    assert r.returncode == 0 and "modified" in r.stdout and "last used" in r.stdout


def test_cli_gc_reclaim_dry_run_json(store):
    s, e = store
    r = _dfm(str(s.parent), "gc", "--store", str(s), "--reclaim", "5M",
             "--dry-run", "--json")
    d = json.loads(r.stdout)
    assert d["kind"] == "store.gc" and d["need"] == 5 * MB and d["size"] >= 5 * MB
    assert os.path.isdir(e["orphan"])


def test_cli_info_size(tmp_path):
    p = tmp_path / "proj"
    (p / "rundir" / "pkg.build").mkdir(parents=True)
    (p / "flow.yaml").write_text("package:\n  name: pkg\n")
    (p / "rundir" / "pkg.build" / "f").write_bytes(b"x" * MB)
    r = subprocess.run([sys.executable, "-m", "dv_flow.mgr", "store", "info",
                        "--size", "--json"], cwd=str(p), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, timeout=60)
    d = json.loads(r.stdout)
    assert d["kind"] == "store.info" and d["stats"]["top"][0][0] == "pkg.build"
