import os
import re
import threading
import time

from dv_flow.mgr.run_id import alloc_run_id, is_run_id, set_latest

_FMT = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
_NOW = time.mktime((2026, 10, 31, 14, 22, 10, 0, 0, -1))


def test_format(tmp_path):
    rid = alloc_run_id(str(tmp_path))
    assert _FMT.match(rid)
    assert os.path.isdir(tmp_path / "out" / rid)


def test_frozen_now_collision(tmp_path):
    a = alloc_run_id(str(tmp_path), now=_NOW)
    b = alloc_run_id(str(tmp_path), now=_NOW)
    assert a == "20261031-142210"
    assert b == "20261031-142210-2"
    assert os.path.isdir(tmp_path / "out" / a)
    assert os.path.isdir(tmp_path / "out" / b)


def test_no_create(tmp_path):
    a = alloc_run_id(str(tmp_path), now=_NOW, create=False)
    assert a == "20261031-142210"
    assert not os.path.exists(tmp_path / "out")
    # Not created, so a second pick returns the same id
    assert alloc_run_id(str(tmp_path), now=_NOW, create=False) == a
    os.makedirs(tmp_path / "out" / a)
    assert alloc_run_id(str(tmp_path), now=_NOW, create=False) == a + "-2"


def test_concurrent(tmp_path):
    ids = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        rid = alloc_run_id(str(tmp_path), now=_NOW)
        with lock:
            ids.append(rid)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == 8
    assert len(set(ids)) == 8
    for rid in ids:
        assert os.path.isdir(tmp_path / "out" / rid)


def test_is_run_id():
    assert is_run_id("20261031-142210")
    assert is_run_id("20261031-142210-2")
    assert is_run_id("0003")
    assert not is_run_id("ci-42")
    assert not is_run_id("latest")
    assert not is_run_id("foo")


def test_set_latest(tmp_path):
    out = tmp_path / "out"
    # Missing out/ and missing link
    set_latest(str(out), "20261031-142210")
    assert os.readlink(out / "latest") == "20261031-142210"
    # Replace an existing link
    set_latest(str(out), "20261031-142211")
    assert os.readlink(out / "latest") == "20261031-142211"
    assert sorted(os.listdir(out)) == ["latest"]
