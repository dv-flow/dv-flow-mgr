import json
import os
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from dv_flow.mgr import data_io
from dv_flow.mgr.task_data import SeverityE


def _mk_item(type, **kw):
    return SimpleNamespace(type=type, **kw)


class _Params(BaseModel):
    top : str = "soc_top"
    seeds : list = [1, 2, 3]
    opts : dict = {"a": 1}
    count : int = 4
    enabled : bool = True


def _mk_input(tmpdir, inputs=None, params=None):
    return SimpleNamespace(
        name="pkg.task",
        srcdir=str(tmpdir),
        rundir=str(tmpdir),
        params=params if params is not None else _Params(),
        inputs=inputs if inputs is not None else [],
        memento=None,
    )


# ---------------------------------------------------------------------------
# stage_inputs
# ---------------------------------------------------------------------------

def test_stage_inputs_params_file_and_scalars(tmpdir):
    inp = _mk_input(tmpdir)
    env = data_io.stage_inputs(str(tmpdir), inp)

    # dfm.params.json matches model_dump
    with open(os.path.join(str(tmpdir), data_io.PARAMS_FILE)) as fp:
        params = json.load(fp)
    assert params == inp.params.model_dump(mode="json")

    # scalars verbatim; list/map compact JSON; bool shell-friendly
    assert env["DFM_PARAM_TOP"] == "soc_top"
    assert env["DFM_PARAM_SEEDS"] == "[1,2,3]"
    assert env["DFM_PARAM_OPTS"] == '{"a":1}'
    assert env["DFM_PARAM_COUNT"] == "4"
    assert env["DFM_PARAM_ENABLED"] == "true"

    # all locating env vars present
    for key in ("DFM_RUNDIR", "DFM_SRCDIR", "DFM_TASK_NAME", "DFM_PARAMS",
                "DFM_INPUTS", "DFM_OUTPUT", "DFM_ENV", "DFM_PATH",
                "DFM_MARKERS", "DFM_MEMENTO_OUT"):
        assert key in env

    # output files pre-created empty
    for fname in (data_io.OUTPUT_FILE, data_io.ENV_FILE,
                  data_io.PATH_FILE, data_io.MARKERS_FILE):
        p = os.path.join(str(tmpdir), fname)
        assert os.path.exists(p)
        assert os.path.getsize(p) == 0


def test_stage_inputs_memento_absent_and_present(tmpdir):
    inp = _mk_input(tmpdir)
    env = data_io.stage_inputs(str(tmpdir), inp, memento=None)
    assert "DFM_MEMENTO" not in env
    assert not os.path.exists(os.path.join(str(tmpdir), data_io.MEMENTO_IN))

    env = data_io.stage_inputs(str(tmpdir), inp, memento={"k": "v"})
    assert "DFM_MEMENTO" in env
    with open(os.path.join(str(tmpdir), data_io.MEMENTO_IN)) as fp:
        assert json.load(fp) == {"k": "v"}


def test_stage_inputs_serializes_inputs(tmpdir):
    fs = SimpleNamespace()
    fs_model = _FsLike(type="std.FileSet", files=["a.sv", "b.sv"])
    inp = _mk_input(tmpdir, inputs=[fs_model])
    data_io.stage_inputs(str(tmpdir), inp)
    with open(os.path.join(str(tmpdir), data_io.INPUTS_FILE)) as fp:
        arr = json.load(fp)
    assert arr == [fs_model.model_dump()]


class _FsLike(BaseModel):
    type : str
    files : list


# ---------------------------------------------------------------------------
# harvest_outputs
# ---------------------------------------------------------------------------

def _write(tmpdir, fname, content):
    with open(os.path.join(str(tmpdir), fname), "w") as fp:
        fp.write(content)


def test_harvest_output_filesets(tmpdir):
    _write(tmpdir, data_io.OUTPUT_FILE,
           '{"type":"std.FileSet","basedir":".","files":["gen.sv"]}\n'
           '\n'  # blank line ignored
           '{"type":"std.FileSet","basedir":"/abs","files":["b.sv"]}\n'
           'not-json\n')  # malformed -> warning marker, not crash
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="pkg.task")
    assert len(res.output) == 2
    # basedir "." rewritten to rundir; order preserved
    assert res.output[0].basedir == str(tmpdir)
    assert res.output[0].files == ["gen.sv"]
    assert res.output[0].src == "pkg.task"
    assert res.output[0].seq == 0
    assert res.output[1].basedir == "/abs"
    assert res.output[1].seq == 1
    # the malformed line produced a warning marker
    assert any(m.severity == SeverityE.Warning for m in res.markers)


def test_harvest_env_plain_and_heredoc(tmpdir):
    _write(tmpdir, data_io.ENV_FILE,
           "SIM_SEED=42\n"
           "BANNER<<EOF\n"
           "line1\n"
           "line2\n"
           "EOF\n")
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.env_item is not None
    assert res.env_item.type == "std.Env"
    assert res.env_item.vals["SIM_SEED"] == "42"
    assert res.env_item.vals["BANNER"] == "line1\nline2"


def test_harvest_path(tmpdir):
    _write(tmpdir, data_io.PATH_FILE, "/opt/a/bin\n/opt/b/bin\n")
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.env_item is not None
    assert res.env_item.prepend_path["PATH"] == os.pathsep.join(["/opt/a/bin", "/opt/b/bin"])


def test_harvest_markers(tmpdir):
    _write(tmpdir, data_io.MARKERS_FILE,
           '{"severity":"error","msg":"boom","loc":{"path":"top.sv","line":10,"pos":3}}\n'
           '{"severity":"bogus","msg":"weird sev"}\n')
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.markers[0].severity == SeverityE.Error
    assert res.markers[0].msg == "boom"
    assert res.markers[0].loc.path == "top.sv"
    assert res.markers[0].loc.line == 10
    # bad severity coerced, not crashed
    assert res.markers[1].severity == SeverityE.Info


def test_harvest_memento(tmpdir):
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.memento is None  # absent
    _write(tmpdir, data_io.MEMENTO_OUT, '{"hash":"abc"}')
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.memento == {"hash": "abc"}
    _write(tmpdir, data_io.MEMENTO_OUT, 'not json')
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.memento is None
    assert any(m.severity == SeverityE.Warning for m in res.markers)


def test_harvest_empty_run(tmpdir):
    # No files at all -> the backward-compat contract
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_mk_item, src_name="t")
    assert res.output == []
    assert res.env_item is None
    assert res.markers == []
    assert res.memento is None


def test_harvest_duck_fallback_on_unknown_type(tmpdir):
    def _failing_mk(type, **kw):
        if type == "unknown.Thing":
            raise Exception("Type unknown.Thing does not exist")
        return _mk_item(type, **kw)
    _write(tmpdir, data_io.OUTPUT_FILE,
           '{"type":"unknown.Thing","x":1}\n')
    res = data_io.harvest_outputs(str(tmpdir), mk_item=_failing_mk, src_name="t")
    assert len(res.output) == 1
    assert res.output[0].type == "unknown.Thing"
    assert res.output[0].x == 1
    assert any(m.severity == SeverityE.Warning for m in res.markers)
