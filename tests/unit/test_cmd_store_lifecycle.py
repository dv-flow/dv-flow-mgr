"""`dfm store migrate / unlink / relink`."""
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import rundir_store, rundir_store_ops
from dv_flow.mgr.rundir_store import RundirError, resolve_rundir
from dv_flow.mgr.rundir_store_entry import (Status, classify, entry_lock,
                                            read_meta)
from dv_flow.mgr.rundir_store_ops import (migrate_rundir, relink_rundir,
                                          unlink_rundir)
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


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    (p / "flow.yaml").write_text(FLOW)
    return p


def _d(tmp_path, name="store"):
    return StoreDecision(root=str(tmp_path / name), provenance="test")


def _local(p):
    (p / "rundir" / "pkg.t").mkdir(parents=True)
    (p / "rundir" / "pkg.t" / "out.txt").write_text("result")
    (p / "rundir" / "top.json").write_text("{}")


# ---------------------------------------------------------------- migrate

def test_migrate_same_fs(tmp_path, proj):
    _local(proj)
    entry = migrate_rundir(str(proj), _d(tmp_path), "demo")
    assert os.path.islink(proj / "rundir")
    assert os.path.realpath(proj / "rundir") == entry
    assert (proj / "rundir" / "pkg.t" / "out.txt").read_text() == "result"
    assert read_meta(entry).link == str(proj / "rundir")
    assert not any(n.startswith("rundir.") for n in os.listdir(proj))


def test_migrate_cross_fs(tmp_path, proj, monkeypatch):
    _local(proj)
    monkeypatch.setattr(rundir_store_ops, "same_fs", lambda a, b: False)
    entry = migrate_rundir(str(proj), _d(tmp_path), "demo")
    assert (proj / "rundir" / "pkg.t" / "out.txt").read_text() == "result"
    assert os.path.isfile(os.path.join(entry, "top.json"))


def test_migrate_rollback(tmp_path, proj, monkeypatch):
    _local(proj)

    def boom(t, l):
        raise OSError("symlink failed")
    monkeypatch.setattr(rundir_store_ops, "atomic_symlink", boom)
    with pytest.raises(OSError):
        migrate_rundir(str(proj), _d(tmp_path), "demo")
    assert os.path.isdir(proj / "rundir") and not os.path.islink(proj / "rundir")
    assert (proj / "rundir" / "pkg.t" / "out.txt").read_text() == "result"


def test_migrate_requires_local_and_store(tmp_path, proj):
    with pytest.raises(RundirError, match="not a local rundir"):
        migrate_rundir(str(proj), _d(tmp_path), "demo")
    _local(proj)
    with pytest.raises(RundirError, match="No rundir store"):
        migrate_rundir(str(proj), StoreDecision(), "demo")


def test_migrate_dry_run(tmp_path, proj):
    _local(proj)
    assert migrate_rundir(str(proj), _d(tmp_path), dry_run=True) == str(tmp_path / "store")
    assert not os.path.islink(proj / "rundir")


def test_migrate_gitignore_warning(tmp_path, proj, capsys):
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    (proj / ".gitignore").write_text("rundir/\n")
    _local(proj)
    migrate_rundir(str(proj), _d(tmp_path), "demo")
    assert "not ignored by git" in capsys.readouterr().err


def test_migrate_then_run_up_to_date(tmp_path, proj):
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-m", "dv_flow.mgr", "run", "hello"],
                       cwd=str(proj), env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, timeout=120)
    assert r.returncode == 0, r.stdout
    migrate_rundir(str(proj), _d(tmp_path), "demo")
    env["DFM_STORE"] = str(tmp_path / "store")
    r = subprocess.run([sys.executable, "-m", "dv_flow.mgr", "run", "hello"],
                       cwd=str(proj), env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, timeout=120)
    assert r.returncode == 0, r.stdout
    assert (proj / "rundir" / "demo.hello" / "out.txt").read_text().strip() == "hi"


# ---------------------------------------------------------------- unlink

def _linked(tmp_path, proj, name="store"):
    info = resolve_rundir(str(proj), store=_d(tmp_path, name), cwd=str(proj),
                          lock=False)
    (proj / "rundir" / "data.txt").write_text("d")
    return info.entry


def test_unlink_local(tmp_path, proj):
    entry = _linked(tmp_path, proj)
    unlink_rundir(str(proj), local=True)
    assert os.path.isdir(proj / "rundir") and not os.path.islink(proj / "rundir")
    assert (proj / "rundir" / "data.txt").read_text() == "d"
    assert not os.path.exists(proj / "rundir" / ".dfm-rundir.json")
    assert not os.path.exists(entry)


def test_unlink_keep(tmp_path, proj):
    entry = _linked(tmp_path, proj)
    unlink_rundir(str(proj), keep=True)
    assert not os.path.lexists(proj / "rundir")
    assert os.path.isdir(entry)
    assert classify(entry, "h") == Status.ORPHAN


def test_unlink_local_keep_is_retargeted(tmp_path, proj):
    entry = _linked(tmp_path, proj)
    unlink_rundir(str(proj), local=True, keep=True)
    assert classify(entry, "h") == Status.RETARGETED


def test_unlink_dangling_local(tmp_path, proj):
    os.symlink(tmp_path / "gone" / "x", proj / "rundir")
    unlink_rundir(str(proj), local=True)
    assert os.path.isdir(proj / "rundir") and not os.path.islink(proj / "rundir")


def test_unlink_not_a_link(proj):
    (proj / "rundir").mkdir()
    with pytest.raises(RundirError):
        unlink_rundir(str(proj))


# ---------------------------------------------------------------- relink

def test_relink_moves_entry(tmp_path, proj):
    old = _linked(tmp_path, proj, "s1")
    new = relink_rundir(str(proj), _d(tmp_path, "s2"), "demo")
    assert os.path.dirname(new) == str(tmp_path / "s2")
    assert os.path.realpath(proj / "rundir") == new
    assert (proj / "rundir" / "data.txt").read_text() == "d"
    assert not os.path.exists(old)
    assert read_meta(new).store_source == "test"


def test_relink_same_store_noop(tmp_path, proj):
    old = _linked(tmp_path, proj)
    assert relink_rundir(str(proj), _d(tmp_path), "demo") == old


def test_relink_dangling(tmp_path, proj):
    os.symlink(tmp_path / "gone" / "x", proj / "rundir")
    new = relink_rundir(str(proj), _d(tmp_path), "demo")
    assert os.path.realpath(proj / "rundir") == new and read_meta(new) is not None


def test_relink_local_refused(tmp_path, proj):
    (proj / "rundir").mkdir()
    with pytest.raises(RundirError, match="migrate"):
        relink_rundir(str(proj), _d(tmp_path), "demo")


# ---------------------------------------------------------------- busy

def test_busy_entry_refused(tmp_path, proj):
    entry = _linked(tmp_path, proj, "s1")
    lk = entry_lock(entry, shared=True)
    assert lk.acquire()
    try:
        with pytest.raises(RundirError, match="in use"):
            unlink_rundir(str(proj), local=True)
        with pytest.raises(RundirError, match="in use"):
            relink_rundir(str(proj), _d(tmp_path, "s2"), "demo")
        assert os.path.islink(proj / "rundir")
    finally:
        lk.release()


# ---------------------------------------------------------------- CLI

def test_cli_migrate_unlink_relink(tmp_path, proj):
    def dfm(*a, **env):
        e = dict(os.environ)
        e.update(env)
        return subprocess.run([sys.executable, "-m", "dv_flow.mgr", "store"] + list(a),
                              cwd=str(proj), env=e, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=60)
    _local(proj)
    r = dfm("migrate", DFM_STORE=str(tmp_path / "s1"))
    assert r.returncode == 0, r.stderr
    assert os.path.islink(proj / "rundir")
    r = dfm("relink", "--store", str(tmp_path / "s2"))
    assert r.returncode == 0, r.stderr
    assert os.path.realpath(proj / "rundir").startswith(str(tmp_path / "s2"))
    r = dfm("unlink", "--local")
    assert r.returncode == 0, r.stderr
    assert not os.path.islink(proj / "rundir")
    r = dfm("unlink")
    assert r.returncode == 1 and "not a rundir link" in r.stderr
