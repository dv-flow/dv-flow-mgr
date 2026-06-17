import json
import os

import pytest

from dv_flow.mgr import out
from dv_flow.mgr import data_io


def _setenv(tmpdir, monkeypatch):
    paths = {}
    for var, fname in (("DFM_OUTPUT", data_io.OUTPUT_FILE),
                       ("DFM_ENV", data_io.ENV_FILE),
                       ("DFM_PATH", data_io.PATH_FILE),
                       ("DFM_MARKERS", data_io.MARKERS_FILE)):
        p = os.path.join(str(tmpdir), fname)
        open(p, "w").close()
        monkeypatch.setenv(var, p)
        paths[var] = p
    return paths


def _lines(path):
    with open(path) as fp:
        return [l for l in fp.read().splitlines() if l.strip()]


def test_fileset(tmpdir, monkeypatch):
    paths = _setenv(tmpdir, monkeypatch)
    assert out.main(["fileset", "--filetype", "verilogSource", "a.sv", "b.sv"]) == 0
    rows = [json.loads(l) for l in _lines(paths["DFM_OUTPUT"])]
    assert rows == [{"type": "std.FileSet", "filetype": "verilogSource",
                     "basedir": ".", "files": ["a.sv", "b.sv"]}]


def test_env_and_path(tmpdir, monkeypatch):
    paths = _setenv(tmpdir, monkeypatch)
    assert out.main(["env", "FOO=bar", "BAZ=qux"]) == 0
    assert _lines(paths["DFM_ENV"]) == ["FOO=bar", "BAZ=qux"]
    assert out.main(["path", "/opt/a/bin", "/opt/b/bin"]) == 0
    assert _lines(paths["DFM_PATH"]) == ["/opt/a/bin", "/opt/b/bin"]


def test_item_typed_values(tmpdir, monkeypatch):
    paths = _setenv(tmpdir, monkeypatch)
    assert out.main(["item", "--type", "my_pkg.Report", "k=v", "n:=3", "flag:=true"]) == 0
    row = json.loads(_lines(paths["DFM_OUTPUT"])[0])
    assert row == {"type": "my_pkg.Report", "k": "v", "n": 3, "flag": True}


def test_markers(tmpdir, monkeypatch):
    paths = _setenv(tmpdir, monkeypatch)
    assert out.main(["error", "boom", "--file", "top.sv", "--line", "10"]) == 0
    assert out.main(["warning", "careful"]) == 0
    rows = [json.loads(l) for l in _lines(paths["DFM_MARKERS"])]
    assert rows[0] == {"severity": "error", "msg": "boom",
                       "loc": {"path": "top.sv", "line": 10}}
    assert rows[1] == {"severity": "warning", "msg": "careful"}


def test_missing_env_var_guard(tmpdir, monkeypatch):
    monkeypatch.delenv("DFM_OUTPUT", raising=False)
    rc = out.main(["fileset", "a.sv"])
    assert rc != 0


def test_env_rejects_bad_token(tmpdir, monkeypatch):
    _setenv(tmpdir, monkeypatch)
    assert out.main(["env", "NOTKV"]) != 0
