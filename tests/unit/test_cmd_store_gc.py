"""`dfm store list` / `gc`: entry classification, selection and deletion."""
import json
import os
import subprocess
import sys

import pytest

from dv_flow.mgr.rundir_store_entry import (
    EntryMeta, Status, classify, entry_lock, now_iso, write_marker, write_meta)
from dv_flow.mgr.rundir_store_ops import (
    EntryFilter, execute_gc, list_entries, parse_duration, plan_gc)

from dv_flow.mgr.site_config import current_host

HOST = current_host()     # the CLI classifies against the real host
OLD = "2000-01-01T00:00:00Z"


def _entry(store, name, link, host=HOST, last_used=OLD, uid=None, user="me",
           meta=True):
    e = store / name
    e.mkdir()
    if meta:
        write_meta(str(e), EntryMeta(
            link=str(link), project_root=os.path.dirname(str(link)),
            user=user, uid=os.getuid() if uid is None else uid, host=host,
            created=last_used, last_used=last_used))
    return e


@pytest.fixture
def store(tmp_path):
    """One entry of each status."""
    s = tmp_path / "store"
    s.mkdir()
    write_marker(str(s))
    projs = tmp_path / "projs"
    projs.mkdir()
    e = {}
    # ok: link points at the entry
    (projs / "ok").mkdir()
    e["ok"] = _entry(s, "ok", projs / "ok" / "rundir")
    os.symlink(e["ok"], projs / "ok" / "rundir")
    # orphan: project deleted (link absent, parent visible)
    e["orphan"] = _entry(s, "orphan", projs / "deleted" / "rundir")
    # retargeted: link is now a real dir
    (projs / "re" / "rundir").mkdir(parents=True)
    e["retargeted"] = _entry(s, "retargeted", projs / "re" / "rundir")
    # unknown: another host, path not visible here
    e["unknown"] = _entry(s, "unknown", "/hostlocal/x/rundir", host="otherhost")
    # busy: a session lock is held
    (projs / "busy").mkdir()
    e["busy"] = _entry(s, "busy", projs / "busy-gone" / "rundir")
    # unmanaged: no metadata
    e["unmanaged"] = _entry(s, "unmanaged", "", meta=False)
    lk = entry_lock(str(e["busy"]), shared=True)
    assert lk.acquire()
    yield s, e
    lk.release()


def test_classify_each(store):
    s, e = store
    for name, path in e.items():
        assert classify(str(path), HOST).value == name, name


def test_orphan_same_host_parent_missing(tmp_path):
    s = tmp_path / "s"
    s.mkdir()
    p = _entry(s, "x", "/no/such/parent/rundir", host=HOST)
    assert classify(str(p), HOST) == Status.ORPHAN
    assert classify(str(p), "elsewhere") == Status.UNKNOWN


def test_list_entries_and_status_filter(store):
    s, e = store
    recs = list_entries(str(s), EntryFilter(), this_host=HOST)
    assert sorted(r.name for r in recs) == sorted(e)
    recs = list_entries(str(s), EntryFilter(statuses=["orphan", "ok"]), this_host=HOST)
    assert sorted(r.name for r in recs) == ["ok", "orphan"]


def test_list_user_filter(tmp_path):
    s = tmp_path / "s"
    s.mkdir()
    _entry(s, "mine", "/x/rundir")
    _entry(s, "theirs", "/y/rundir", uid=os.getuid() + 1, user="bob")
    assert [r.name for r in list_entries(str(s), EntryFilter())] == ["mine"]
    assert [r.name for r in list_entries(str(s), EntryFilter(user="bob"))] == ["theirs"]
    assert len(list_entries(str(s), EntryFilter(all_users=True))) == 2


def test_list_size(tmp_path):
    s = tmp_path / "s"
    s.mkdir()
    e = _entry(s, "e", "/x/rundir")
    (e / "d").mkdir()
    (e / "d" / "f").write_bytes(b"x" * 1000)
    r = list_entries(str(s), with_size=True)[0]
    assert r.size >= 1000


def test_plan_default_orphans(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), this_host=HOST)
    assert sorted(c.rec.name for c in plan.delete) == ["orphan", "retargeted"]
    assert [c.rec.name for c in plan.skipped] == ["busy"]


def test_plan_include_unknown(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), include_unknown=True, this_host=HOST)
    assert sorted(c.rec.name for c in plan.delete) == ["orphan", "retargeted", "unknown"]


def test_older_than_alone_selects_linked(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), older_than=parse_duration("30d"),
                   this_host=HOST)
    names = sorted(c.rec.name for c in plan.delete)
    assert "ok" in names and "busy" not in names and "unmanaged" not in names


def test_older_than_and_orphans(tmp_path):
    s = tmp_path / "s"
    s.mkdir()
    _entry(s, "old", tmp_path / "gone1" / "rundir")
    _entry(s, "new", tmp_path / "gone2" / "rundir", last_used=now_iso())
    plan = plan_gc(str(s), EntryFilter(), orphans=True,
                   older_than=parse_duration("1d"), this_host=HOST)
    assert [c.rec.name for c in plan.delete] == ["old"]


def test_recent_entries_skipped_without_force(tmp_path):
    s = tmp_path / "s"
    s.mkdir()
    _entry(s, "fresh", tmp_path / "gone" / "rundir", last_used=now_iso())
    plan = plan_gc(str(s), EntryFilter(), this_host=HOST)
    assert plan.delete == [] and plan.skipped[0].reason.startswith("used within")
    plan = plan_gc(str(s), EntryFilter(), force=True, this_host=HOST)
    assert [c.rec.name for c in plan.delete] == ["fresh"]


def test_execute_gc(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), include_unknown=True, this_host=HOST)
    removed, failed = execute_gc(str(s), plan, this_host=HOST)
    assert failed == []
    left = sorted(n for n in os.listdir(s) if not n.startswith("."))
    assert left == ["busy", "ok", "unmanaged"]


def test_execute_gc_rechecks_status(store):
    s, e = store
    plan = plan_gc(str(s), EntryFilter(), this_host=HOST)
    # The orphan's project comes back before deletion.
    projs = s.parent / "projs"
    (projs / "deleted").mkdir()
    os.symlink(e["orphan"], projs / "deleted" / "rundir")
    removed, failed = execute_gc(str(s), plan, this_host=HOST)
    assert os.path.isdir(e["orphan"])
    assert any("status changed" in err for _, err in failed)


@pytest.mark.parametrize("s,secs", [("30d", 30 * 86400), ("12h", 43200),
                                    ("2w", 14 * 86400), ("90m", 5400), ("7", 7 * 86400)])
def test_parse_duration(s, secs):
    assert parse_duration(s) == secs


def test_parse_duration_bad():
    with pytest.raises(ValueError):
        parse_duration("soon")


# ---------------------------------------------------------------- CLI

def _dfm(cwd, *args):
    return subprocess.run([sys.executable, "-m", "dv_flow.mgr"] + list(args),
                          cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=60, stdin=subprocess.DEVNULL)


def test_cli_gc_dry_run_deletes_nothing(store):
    s, e = store
    entries = lambda: sorted(n for n in os.listdir(s) if not n.startswith("."))
    before = entries()
    r = _dfm(str(s.parent), "store", "gc", "--store", str(s), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "orphan" in r.stdout
    assert entries() == before


def test_cli_gc_needs_yes_without_tty(store):
    s, e = store
    r = _dfm(str(s.parent), "store", "gc", "--store", str(s))
    assert r.returncode != 0 and "-y" in r.stderr
    assert os.path.isdir(e["orphan"])


def test_cli_gc_yes(store):
    s, e = store
    r = _dfm(str(s.parent), "store", "gc", "--store", str(s), "-y")
    assert r.returncode == 0, r.stderr + r.stdout
    assert not os.path.exists(e["orphan"]) and os.path.isdir(e["ok"])


def test_cli_gc_refuses_without_marker(tmp_path):
    (tmp_path / "notastore").mkdir()
    r = _dfm(str(tmp_path), "store", "gc", "--store", str(tmp_path / "notastore"), "-y")
    assert r.returncode != 0 and "not a rundir store" in r.stderr


def test_cli_list_json(store):
    s, e = store
    r = _dfm(str(s.parent), "store", "list", "--store", str(s), "--json", "--size")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    st = {x["name"]: x["status"] for x in d["entries"]}
    assert st["orphan"] == "orphan" and st["unmanaged"] == "unmanaged"
    assert all(x["size"] is not None for x in d["entries"])


def test_gc_then_run_recovers_dangling(tmp_path):
    """Deleting a still-linked entry (gc --older-than) leaves a dangling link
    that the next run recreates."""
    from dv_flow.mgr.rundir_store import resolve_rundir
    from dv_flow.mgr.store_config import StoreDecision
    p = tmp_path / "proj"
    p.mkdir()
    d = StoreDecision(root=str(tmp_path / "s"), provenance="t")
    info = resolve_rundir(str(p), store=d, cwd=str(p), lock=False)
    from dv_flow.mgr.rundir_store_entry import read_meta
    m = read_meta(info.entry)
    m.last_used = OLD
    write_meta(info.entry, m)
    plan = plan_gc(str(tmp_path / "s"), EntryFilter(), older_than=86400)
    removed, failed = execute_gc(str(tmp_path / "s"), plan)
    assert len(removed) == 1 and not os.path.exists(info.entry)
    info2 = resolve_rundir(str(p), store=d, cwd=str(p), lock=False)
    assert os.path.isdir(info2.entry)
