"""Rundir store entries: naming, metadata, creation, copy/move detection,
dangling links, the session lock, and `dfm run` in store mode."""
import json
import os
import stat
import subprocess
import sys
import threading

import pytest

from dv_flow.mgr import rundir_store
from dv_flow.mgr.rundir_store import RundirError, resolve_rundir
from dv_flow.mgr.rundir_store_entry import (
    EntryLock, EntryMeta, MAX_NAME, entry_lock, hashed_name, is_store_root,
    mangle, read_meta, write_meta)
from dv_flow.mgr.store_config import StoreDecision

FLOW = """\
package:
  name: demo
  tasks:
  - name: hello
    shell: bash
    run: echo hi > out.txt
"""


@pytest.fixture(autouse=True)
def reset_notes():
    rundir_store._notes_shown.clear()


def _proj(tmp_path, name="proj"):
    p = tmp_path / name
    p.mkdir(parents=True)
    (p / "flow.yaml").write_text(FLOW)
    return p


def _store(tmp_path, name="store", **kw):
    return StoreDecision(root=str(tmp_path / name), provenance="test", **kw)


def _resolve(p, store, **kw):
    kw.setdefault("lock", False)
    return resolve_rundir(str(p), store=store, package="demo", cwd=str(p), **kw)


# ---------------------------------------------------------------- naming

def test_mangle_example():
    assert mangle("/home/u/p/rundir") == "_home_u_p_rundir"


def test_mangle_length():
    long = "/" + "/".join(["d" * 50] * 10) + "/rundir"
    n = mangle(long)
    assert len(n.encode()) <= MAX_NAME and "__" in n
    assert mangle(long) == n                          # stable
    multibyte = "/" + "/".join(["é" * 40] * 6) + "/rundir"
    assert len(mangle(multibyte).encode()) <= MAX_NAME
    assert len(hashed_name(long, "h", 1).encode()) <= MAX_NAME


def test_meta_roundtrip(tmp_path):
    m = EntryMeta(link="/a/rundir", project_root="/a", uid=5, host="h",
                  git={"remote": "r", "branch": "b"})
    write_meta(str(tmp_path), m)
    assert read_meta(str(tmp_path)) == m
    assert [f for f in os.listdir(tmp_path) if ".tmp" in f] == []


def test_meta_write_failure_leaves_no_tmp(tmp_path, monkeypatch):
    def boom(*a):
        raise OSError("boom")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_meta(str(tmp_path), EntryMeta(link="/a", project_root="/"))
    assert os.listdir(tmp_path) == []


# ---------------------------------------------------------------- creation

def test_fresh_entry_and_link(tmp_path):
    p = _proj(tmp_path)
    info = _resolve(p, _store(tmp_path))
    L = p / "rundir"
    assert os.path.islink(L)
    assert info.path == str(L)
    assert info.state == "ok"
    entry = os.path.realpath(L)
    assert os.path.dirname(entry) == str(tmp_path / "store")
    assert os.path.basename(entry) == mangle(str(L))
    assert is_store_root(str(tmp_path / "store"))
    m = read_meta(entry)
    assert m.link == str(L) and m.project_root == str(p)
    assert m.package == "demo" and m.uid == os.getuid()
    assert m.store_source == "test" and m.created and m.last_used


def test_second_resolve_reuses_and_touches(tmp_path):
    p = _proj(tmp_path)
    info1 = _resolve(p, _store(tmp_path))
    m = read_meta(info1.entry)
    m.last_used = "2000-01-01T00:00:00Z"
    write_meta(info1.entry, m)
    info2 = _resolve(p, _store(tmp_path))
    assert info2.entry == info1.entry
    assert read_meta(info2.entry).last_used != "2000-01-01T00:00:00Z"


def test_name_collision_uses_hash(tmp_path):
    a = tmp_path / "a_b"
    b = tmp_path / "a" / "b"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "flow.yaml").write_text(FLOW)
    ia = _resolve(a, _store(tmp_path))
    ib = _resolve(b, _store(tmp_path))
    assert ia.entry != ib.entry
    assert os.path.basename(ia.entry) == mangle(str(a / "rundir"))
    assert os.path.basename(ib.entry).startswith(mangle(str(b / "rundir")) + "__")


def test_concurrent_create_single_entry(tmp_path):
    p = _proj(tmp_path)
    errs = []

    def go():
        try:
            _resolve(p, _store(tmp_path))
        except Exception as e:     # pragma: no cover - reported below
            errs.append(e)
    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errs == []
    entries = [e for e in os.listdir(tmp_path / "store") if not e.startswith(".")]
    assert len(entries) == 1


def test_store_root_autocreate(tmp_path):
    p = _proj(tmp_path)
    _resolve(p, _store(tmp_path, "newstore"))
    assert is_store_root(str(tmp_path / "newstore"))


def test_store_root_parent_missing(tmp_path):
    p = _proj(tmp_path)
    with pytest.raises(RundirError, match="mounted"):
        _resolve(p, StoreDecision(root=str(tmp_path / "nomnt" / "s"), provenance="t"))
    assert not os.path.lexists(p / "rundir")


def test_store_root_create_false(tmp_path):
    p = _proj(tmp_path)
    with pytest.raises(RundirError, match="store.create"):
        _resolve(p, _store(tmp_path, create=False))


def test_local_rundir_stays_local_with_hint(tmp_path, capsys):
    p = _proj(tmp_path)
    (p / "rundir").mkdir()
    info = _resolve(p, _store(tmp_path))
    _resolve(p, _store(tmp_path))
    assert info.state == "local" and not os.path.islink(p / "rundir")
    assert capsys.readouterr().err.count("dfm store migrate") == 1


def test_sticky_link_reports_mismatch(tmp_path):
    p = _proj(tmp_path)
    i1 = _resolve(p, _store(tmp_path, "s1"))
    i2 = _resolve(p, _store(tmp_path, "s2"))
    assert i2.entry == i1.entry and i2.mismatch
    assert not os.path.exists(tmp_path / "s2")


# ---------------------------------------------------------------- copy / move

def test_copied_project_forks(tmp_path, capsys):
    p = _proj(tmp_path)
    i1 = _resolve(p, _store(tmp_path))
    (p / "rundir" / "result").write_text("orig")
    import shutil
    shutil.copytree(p, tmp_path / "copy", symlinks=True)
    i2 = _resolve(tmp_path / "copy", _store(tmp_path))
    assert i2.entry != i1.entry
    assert os.path.realpath(p / "rundir") == i1.entry      # original untouched
    assert os.path.realpath(tmp_path / "copy" / "rundir") == i2.entry
    assert read_meta(i2.entry).link == str(tmp_path / "copy" / "rundir")
    assert not os.path.exists(os.path.join(i2.entry, "result"))
    assert "copied" in capsys.readouterr().err


def test_moved_project_adopted(tmp_path):
    p = _proj(tmp_path)
    i1 = _resolve(p, _store(tmp_path))
    (p / "rundir" / "result").write_text("keep")
    os.rename(p, tmp_path / "moved")
    q = tmp_path / "moved"
    i2 = _resolve(q, _store(tmp_path))
    assert os.path.basename(i2.entry) == mangle(str(q / "rundir"))
    assert not os.path.exists(i1.entry)
    assert os.path.realpath(q / "rundir") == i2.entry
    assert (q / "rundir" / "result").read_text() == "keep"
    m = read_meta(i2.entry)
    assert m.link == str(q / "rundir") and m.project_root == str(q)


def test_store_dir_without_meta_is_adopted(tmp_path):
    p = _proj(tmp_path)
    s = tmp_path / "store"
    s.mkdir()
    (s / ".dfm-store.yaml").write_text("version: 1\n")
    (s / "handmade").mkdir()
    os.symlink(s / "handmade", p / "rundir")
    info = _resolve(p, _store(tmp_path))
    assert info.state == "ok" and read_meta(str(s / "handmade")).link == str(p / "rundir")


# ---------------------------------------------------------------- dangling

def test_dangling_in_store_recreated_with_meta(tmp_path, capsys):
    p = _proj(tmp_path)
    i1 = _resolve(p, _store(tmp_path))
    import shutil
    shutil.rmtree(i1.entry)
    i2 = _resolve(p, _store(tmp_path))
    assert i2.entry == i1.entry and os.path.isdir(i2.entry)
    assert read_meta(i2.entry).store_source == "recreated"
    assert "recreated" in capsys.readouterr().err


def test_dangling_store_unmounted_error(tmp_path):
    p = _proj(tmp_path)
    os.symlink(tmp_path / "gone" / "_x_rundir", p / "rundir")
    with pytest.raises(RundirError) as ei:
        _resolve(p, _store(tmp_path))
    assert "dfm store relink" in str(ei.value)
    assert "--store-recreate" in str(ei.value)


def test_dangling_store_recreate(tmp_path):
    p = _proj(tmp_path)
    os.symlink(tmp_path / "gone" / "_x_rundir", p / "rundir")
    info = _resolve(p, _store(tmp_path), recreate=True)
    assert os.path.dirname(info.entry) == str(tmp_path / "store")
    assert os.path.realpath(p / "rundir") == info.entry


def test_dangling_store_recreate_env(tmp_path, monkeypatch):
    p = _proj(tmp_path)
    os.symlink(tmp_path / "gone" / "_x_rundir", p / "rundir")
    monkeypatch.setenv("DFM_STORE_RECREATE", "1")
    info = _resolve(p, _store(tmp_path))
    assert os.path.dirname(info.entry) == str(tmp_path / "store")


# ---------------------------------------------------------------- lock

def test_session_lock_blocks_exclusive(tmp_path):
    p = _proj(tmp_path)
    info = resolve_rundir(str(p), store=_store(tmp_path), cwd=str(p))
    assert info.lock is not None and info.lock.held
    ex = entry_lock(info.entry, shared=False)
    assert not ex.acquire(blocking=False)
    sh = entry_lock(info.entry, shared=True)
    assert sh.acquire(blocking=False)
    sh.release()
    info.close()
    assert ex.acquire(blocking=False)
    ex.release()


def test_lock_fd_cloexec(tmp_path):
    import fcntl
    lk = EntryLock(str(tmp_path / "l"))
    assert lk.acquire()
    assert fcntl.fcntl(lk._fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
    lk.release()


# ---------------------------------------------------------------- dfm CLI

def _dfm(cwd, *args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "dv_flow.mgr"] + list(args),
                          cwd=cwd, env=e, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=120)


def test_dfm_run_store_mode_and_clean(tmp_path):
    p = _proj(tmp_path)
    env = {"DFM_STORE": str(tmp_path / "store")}
    r = _dfm(str(p), "run", "hello", env=env)
    assert r.returncode == 0, r.stdout
    L = p / "rundir"
    assert os.path.islink(L)
    entry = os.path.realpath(L)
    assert os.path.isfile(os.path.join(entry, "demo.hello", "out.txt"))
    # Second run: up-to-date through the symlink
    r = _dfm(str(p), "run", "-v", "hello", env=env)
    assert r.returncode == 0, r.stdout
    r = _dfm(str(p), "run", "--clean", "hello", env=env)
    assert r.returncode == 0, r.stdout
    assert os.path.islink(L) and os.path.realpath(L) == entry
    assert os.path.isfile(os.path.join(entry, ".dfm-rundir.json"))


def test_dfm_run_no_store_flag(tmp_path):
    p = _proj(tmp_path)
    r = _dfm(str(p), "run", "--no-store", "hello",
             env={"DFM_STORE": str(tmp_path / "store")})
    assert r.returncode == 0, r.stdout
    assert os.path.isdir(p / "rundir") and not os.path.islink(p / "rundir")


def test_dfm_run_dangling_error_exit(tmp_path):
    p = _proj(tmp_path)
    os.symlink(tmp_path / "gone" / "x", p / "rundir")
    r = _dfm(str(p), "run", "hello", env={"DFM_STORE": str(tmp_path / "store")})
    assert r.returncode != 0
    assert "does not exist" in r.stdout


def test_dfm_store_init_modes(tmp_path):
    r = _dfm(str(tmp_path), "store", "init", str(tmp_path / "s1"), "--shared")
    assert r.returncode == 0, r.stdout
    assert stat.S_IMODE(os.stat(tmp_path / "s1").st_mode) == 0o1777
    assert is_store_root(str(tmp_path / "s1"))
    r = _dfm(str(tmp_path), "store", "init", str(tmp_path / "s2"), "--group")
    assert stat.S_IMODE(os.stat(tmp_path / "s2").st_mode) == 0o2775
    r = _dfm(str(tmp_path), "store", "init", str(tmp_path / "s2"), "--group")
    assert r.returncode == 0 and "already" in r.stdout


@pytest.mark.parametrize("setup,state", [
    ("none", "none"), ("local", "local"), ("store", "ok"), ("dangling", "dangling")])
def test_dfm_store_info_json(tmp_path, setup, state):
    p = _proj(tmp_path)
    env = {"DFM_STORE": str(tmp_path / "store")}
    if setup == "local":
        (p / "rundir").mkdir()
    elif setup == "store":
        _resolve(p, _store(tmp_path))
    elif setup == "dangling":
        os.symlink(tmp_path / "gone" / "x", p / "rundir")
    r = _dfm(str(p), "store", "info", "--json", env=env)
    assert r.returncode == 0, r.stdout
    d = json.loads(r.stdout)
    assert d["state"] == state
    assert d["store"] == str(tmp_path / "store")
    assert d["provenance"] == "env:DFM_STORE"
    assert d["rundir"] == str(p / "rundir")
