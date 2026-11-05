"""Phase 1 of the rundir store: rundir at the package root, symlink safety,
dangling links, --clean semantics, base-rundir rebasing."""
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import rundir_store
from dv_flow.mgr.rundir_store import (
    RundirError, clean_rundir, find_pkg_root, inspect_rundir, resolve_rundir,
    rundir_path)
from dv_flow.mgr.store_config import StoreDecision
from dv_flow.mgr.task_runner import _rebase_path
from dv_flow.mgr.util.util import find_root_flow_file

LOCAL = StoreDecision()

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
    yield
    rundir_store._notes_shown.clear()


def _proj(tmp_path, name="proj"):
    p = tmp_path / name
    (p / "sub" / "deeper").mkdir(parents=True)
    (p / "flow.yaml").write_text(FLOW)
    return p


class _Args:
    def __init__(self, root=None, **kw):
        self.root = root
        self.__dict__.update(kw)


# ---------------------------------------------------------------- finder

def test_find_root_flow_file_walks_up(tmp_path):
    p = _proj(tmp_path)
    assert find_root_flow_file(str(p / "sub" / "deeper")) == str(p / "flow.yaml")


def test_find_root_flow_file_skips_fragment(tmp_path):
    p = _proj(tmp_path)
    (p / "sub" / "flow.yaml").write_text("fragment:\n  tasks: []\n")
    assert find_root_flow_file(str(p / "sub")) == str(p / "flow.yaml")


def test_find_root_flow_file_none(tmp_path):
    (tmp_path / "x").mkdir()
    assert find_root_flow_file(str(tmp_path / "x")) is None


def test_find_pkg_root_uses_root_arg(tmp_path):
    p = _proj(tmp_path)
    assert find_pkg_root(_Args(root=str(p / "sub"))) == str(p)


# ---------------------------------------------------------------- location

def test_rundir_at_pkg_root_from_subdir(tmp_path, capsys):
    p = _proj(tmp_path)
    info = resolve_rundir(str(p), store=LOCAL, cwd=str(p / "sub"))
    assert info.path == str(p / "rundir")
    assert info.state == "local"
    assert os.path.isdir(p / "rundir")
    assert not os.path.exists(p / "sub" / "rundir")


def test_stale_subdir_rundir_note_once(tmp_path, capsys):
    p = _proj(tmp_path)
    (p / "sub" / "rundir").mkdir()
    resolve_rundir(str(p), store=LOCAL, cwd=str(p / "sub"))
    resolve_rundir(str(p), store=LOCAL, cwd=str(p / "sub"))
    err = capsys.readouterr().err
    assert err.count("is no longer used") == 1


def test_no_package_falls_back_to_cwd(tmp_path, capsys):
    info = resolve_rundir(None, store=LOCAL, cwd=str(tmp_path))
    assert info.path == str(tmp_path / "rundir")
    assert os.path.isdir(tmp_path / "rundir")
    assert "no flow.yaml" in capsys.readouterr().err


def test_create_false_touches_nothing(tmp_path):
    p = _proj(tmp_path)
    info = resolve_rundir(str(p), create=False)
    assert info.path == str(p / "rundir")
    assert not os.path.lexists(p / "rundir")
    assert rundir_path(str(p)) == str(p / "rundir")


def test_regular_file_is_error(tmp_path):
    p = _proj(tmp_path)
    (p / "rundir").write_text("x")
    with pytest.raises(RundirError):
        resolve_rundir(str(p), store=LOCAL)


# ---------------------------------------------------------------- symlinks

def test_handmade_symlink_used_as_is(tmp_path):
    p = _proj(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    os.symlink(target, p / "rundir")
    info = resolve_rundir(str(p), store=LOCAL)
    assert info.state == "unmanaged-symlink"
    assert info.path == str(p / "rundir")      # logical path, not resolved
    assert info.entry == str(target)
    assert not (target / ".dfm-rundir.json").exists()


def test_dangling_recreated_when_parent_exists(tmp_path, capsys):
    p = _proj(tmp_path)
    target = tmp_path / "gone"
    os.symlink(target, p / "rundir")
    info = resolve_rundir(str(p), store=LOCAL)
    assert os.path.isdir(target)
    assert info.state == "unmanaged-symlink"
    assert "recreated" in capsys.readouterr().err


def test_dangling_error_when_parent_missing(tmp_path):
    p = _proj(tmp_path)
    os.symlink(tmp_path / "nomount" / "entry", p / "rundir")
    with pytest.raises(RundirError) as ei:
        resolve_rundir(str(p), store=LOCAL)
    msg = str(ei.value)
    assert "does not exist" in msg and "dfm store unlink --local" in msg
    assert not os.path.exists(tmp_path / "nomount")


def test_inspect_states(tmp_path):
    p = _proj(tmp_path)
    L = str(p / "rundir")
    assert inspect_rundir(L).state == "none"
    os.mkdir(L)
    assert inspect_rundir(L).state == "local"
    os.rmdir(L)
    os.symlink(tmp_path / "missing", L)
    assert inspect_rundir(L).state == "dangling"


# ---------------------------------------------------------------- clean

def test_clean_rundir_keeps_link_and_metadata(tmp_path):
    p = _proj(tmp_path)
    target = tmp_path / "entry"
    target.mkdir()
    (target / ".dfm-rundir.json").write_text("{}")
    (target / ".dfm-rundir.lock").write_text("")
    (target / "task").mkdir()
    (target / "task" / "f").write_text("x")
    (target / "log.txt").write_text("x")
    (target / "lnk").symlink_to(tmp_path / "nowhere")
    os.symlink(target, p / "rundir")
    clean_rundir(str(p / "rundir"))
    assert os.path.islink(p / "rundir")
    assert sorted(os.listdir(target)) == [".dfm-rundir.json", ".dfm-rundir.lock"]


def test_clean_rundir_local(tmp_path):
    d = tmp_path / "rundir"
    (d / "a").mkdir(parents=True)
    clean_rundir(str(d))
    assert os.path.isdir(d) and os.listdir(d) == []


# ---------------------------------------------------------------- base-rundir

def test_rebase_path_component_match():
    assert _rebase_path("/x/rundir/t/out", "/x/rundir", "/b/t") == "/b/t/t/out"
    assert _rebase_path("/x/rundir", "/x/rundir", "/b") == "/b"
    # /x/rundir must not match /x/rundir2
    assert _rebase_path("/x/rundir2/t", "/x/rundir", "/b") == "/x/rundir2/t"
    assert _rebase_path("/elsewhere/f", "/x/rundir", "/b") == "/elsewhere/f"


def test_rebase_path_resolved_form(tmp_path):
    real = tmp_path / "store" / "entry"
    real.mkdir(parents=True)
    link = tmp_path / "rundir"
    os.symlink(real, link)
    # exec_data recorded the logical path, the output recorded the realpath
    out = os.path.join(os.path.realpath(real), "pkg.t", "f.txt")
    assert _rebase_path(out, str(link), "/base") == "/base/pkg.t/f.txt"


# ---------------------------------------------------------------- dfm run

def _dfm(cwd, *args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "dv_flow.mgr"] + list(args),
                          cwd=cwd, env=e, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=120)


def test_dfm_run_from_subdir_uses_pkg_root(tmp_path):
    p = _proj(tmp_path)
    r = _dfm(str(p / "sub"), "run", "hello")
    assert r.returncode == 0, r.stdout
    assert os.path.isfile(p / "rundir" / "demo.hello" / "out.txt")
    assert not os.path.exists(p / "sub" / "rundir")


def test_dfm_run_clean_through_handmade_symlink(tmp_path):
    p = _proj(tmp_path)
    target = tmp_path / "scratch"
    target.mkdir()
    os.symlink(target, p / "rundir")
    r = _dfm(str(p), "run", "hello")
    assert r.returncode == 0, r.stdout
    assert os.path.isfile(target / "demo.hello" / "out.txt")
    r = _dfm(str(p), "run", "--clean", "hello")
    assert r.returncode == 0, r.stdout
    assert os.path.islink(p / "rundir")
    assert os.path.isfile(target / "demo.hello" / "out.txt")
