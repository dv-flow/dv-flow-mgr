import asyncio
import json
import os
import sys
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.std.publish import _Policy, _place, _join, _select


@pytest.fixture(autouse=True)
def reset_extrgy():
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']


def _run(tmpdir, flow_dv):
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
    task = builder.mkTaskNode("test_pkg.publish")
    asyncio.run(runner.run(task))
    return rundir, runner


#*** Path algebra (§4.2) ***************************************************

def test_place_mirror():
    assert _place(_Policy("", 0, False), "core/top.sv", "/b") == "core/top.sv"

def test_place_named_dir():
    assert _place(_Policy("rtl", 0, False), "core/top.sv", "/b") == "rtl/core/top.sv"

def test_place_strip():
    assert _place(_Policy("rtl", 1, False), "core/top.sv", "/b") == "rtl/top.sv"

def test_place_strip_flatten_equiv():
    assert _place(_Policy("", 2, False), "core/top.sv", "/b") == "top.sv"

def test_place_flatten():
    assert _place(_Policy("pub", 0, True), "a/b/c.h", "/b") == "pub/c.h"

def test_place_graft_basedir():
    assert _place(_Policy("", -1, False), "core/top.sv", "/w/rundir/gen.rtl") \
        == "gen.rtl/core/top.sv"

def test_place_strip_clamps_to_basename():
    assert _place(_Policy("", 5, False), "core/top.sv", "/b") == "top.sv"

def test_join_empty_identity():
    assert _join("", "include") == "include"
    assert _join("pub", "") == "pub"
    assert _join("pub", "include") == os.path.join("pub", "include")

def test_select_include_glob():
    class FS:
        files = ["a.h", "b.sv", "sub/c.h"]
    # empty include -> all files
    assert _select(FS(), []) == ["a.h", "b.sv", "sub/c.h"]
    # fnmatch '*' spans '/' (standard fnmatch semantics): *.h matches nested too
    assert _select(FS(), ["*.h"]) == ["a.h", "sub/c.h"]
    # a segment-anchored pattern selects only the top-level header
    assert _select(FS(), ["?.h"]) == ["a.h"]


#*** End-to-end **********************************************************

def test_publish_single(tmpdir):
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_hdr
    uses: std.CreateFile
    with:
      type: verilogInclude
      filename: include/dma.h
      content: "// dma\\n"
  - name: publish
    uses: std.Publish
    needs: [mk_hdr]
    with:
      dest: pub/include
      strip: 1
"""
    rundir, runner = _run(tmpdir, flow)
    assert runner.status == 0
    out = os.path.join(rundir, "out", "0001")
    assert os.path.isfile(os.path.join(out, "pub/include/dma.h"))
    # latest symlink resolves to the run dir
    latest = os.path.join(rundir, "out", "latest")
    assert os.path.islink(latest)
    assert os.readlink(latest) == "0001"
    # provenance manifest
    with open(os.path.join(out, ".dfm-publish.json")) as fp:
        m = json.load(fp)
    assert m["schema"] == "dvflow-publish/1"
    e = m["entries"]["pub/include/dma.h"]
    assert e["src_path"] == "include/dma.h"
    assert "sha256" in e and e["bytes"] > 0


def test_publish_pubset_funnel(tmpdir):
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_hdr
    uses: std.CreateFile
    with:
      type: verilogInclude
      filename: include/dma.h
      content: "H\\n"
  - name: hdr_pubset
    uses: std.PubSet
    needs: [mk_hdr]
    with:
      dest: include
      strip: 1
  - name: mk_readme
    uses: std.CreateFile
    with:
      type: text
      filename: README.md
      content: "R\\n"
  - name: publish
    uses: std.Publish
    needs: [hdr_pubset, mk_readme]
    with:
      dest: pub
"""
    rundir, runner = _run(tmpdir, flow)
    assert runner.status == 0
    out = os.path.join(rundir, "out", "0001")
    # PubSet: pub (task) / include (pubset) / strip 1 -> dma.h
    assert os.path.isfile(os.path.join(out, "pub/include/dma.h"))
    # bare FileSet: task default -> pub/README.md
    assert os.path.isfile(os.path.join(out, "pub/README.md"))


def test_publish_conflict_error(tmpdir):
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_a
    uses: std.CreateFile
    with:
      type: t
      filename: top.sv
      content: "AAA\\n"
  - name: mk_b
    uses: std.CreateFile
    with:
      type: t
      filename: top.sv
      content: "BBB\\n"
  - name: publish
    uses: std.Publish
    needs: [mk_a, mk_b]
    with:
      dest: rtl
"""
    rundir, runner = _run(tmpdir, flow)
    # different content at the same dst -> conflict -> non-zero status
    assert runner.status != 0


def test_publish_run_counter_increments(tmpdir):
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_hdr
    uses: std.CreateFile
    with:
      type: verilogInclude
      filename: dma.h
      content: "H\\n"
  - name: publish
    uses: std.Publish
    needs: [mk_hdr]
    with:
      dest: pub
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)
    loader, pkg_def = loadProjPkgDef(tmpdir)

    for expect in ("0001", "0002", "0003"):
        builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
        assert builder.run_id == expect
        runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
        asyncio.run(runner.run(builder.mkTaskNode("test_pkg.publish")))
        assert runner.status == 0
        assert os.path.isfile(os.path.join(rundir, "out", expect, "pub/dma.h"))

    # latest tracks the newest run
    assert os.readlink(os.path.join(rundir, "out", "latest")) == "0003"


def test_publish_explicit_run_id(tmpdir):
    tmpdir = str(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_hdr
    uses: std.CreateFile
    with:
      type: verilogInclude
      filename: dma.h
      content: "H\\n"
  - name: publish
    uses: std.Publish
    needs: [mk_hdr]
    with:
      dest: pub
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)
    loader, pkg_def = loadProjPkgDef(tmpdir)
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader,
                               run_id="ci-42")
    assert builder.run_id == "ci-42"
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)
    asyncio.run(runner.run(builder.mkTaskNode("test_pkg.publish")))
    assert os.path.isfile(os.path.join(rundir, "out", "ci-42", "pub/dma.h"))


def test_dfm_out_publish_cli(tmpdir):
    from dv_flow.mgr.std.publish import run_publish_cli
    tmpdir = str(tmpdir)
    out_dir = os.path.join(tmpdir, "rundir", "out", "0001")
    src = os.path.join(tmpdir, "work")
    os.makedirs(os.path.join(src, "include"))
    with open(os.path.join(src, "include", "dma.h"), "w") as f:
        f.write("// dma\n")

    status, published, markers = run_publish_cli(
        out_dir=out_dir, run_id="0001", files=["include/dma.h"], basedir=src,
        dest="pub/include", strip=1, flatten=False, include=[],
        on_conflict="error", filetype="verilogInclude", src="gen",
        publish_task="gen")

    assert status == 0
    assert published == ["pub/include/dma.h"]
    assert os.path.isfile(os.path.join(out_dir, "pub/include/dma.h"))
    # latest is created one level up from out_dir
    assert os.readlink(os.path.join(tmpdir, "rundir", "out", "latest")) == "0001"
    m = json.load(open(os.path.join(out_dir, ".dfm-publish.json")))
    assert m["entries"]["pub/include/dma.h"]["src_task"] == "gen"


def test_dfm_out_publish_subprocess(tmpdir):
    tmpdir = str(tmpdir)
    out_dir = os.path.join(tmpdir, "rundir", "out", "0001")
    work = os.path.join(tmpdir, "work")
    os.makedirs(work)
    with open(os.path.join(work, "a.txt"), "w") as f:
        f.write("A\n")
    dfm_output = os.path.join(work, "out.jsonl")
    env = os.environ.copy()
    env["DFM_OUT_DIR"] = out_dir
    env["DFM_RUN_ID"] = "0001"
    env["DFM_TASK_NAME"] = "shelltask"
    env["DFM_OUTPUT"] = dfm_output
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr.out", "publish", "--dest", "d", "a.txt"],
        cwd=work, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.path.isfile(os.path.join(out_dir, "d/a.txt"))
    # the verb emits a std.FileSet to $DFM_OUTPUT
    item = json.loads(open(dfm_output).read().strip())
    assert item["type"] == "std.FileSet"
    assert item["basedir"] == out_dir
    assert item["files"] == ["d/a.txt"]


def test_publish_benign_duplicate(tmpdir):
    flow = """
package:
  name: test_pkg
  tasks:
  - name: mk_a
    uses: std.CreateFile
    with:
      type: t
      filename: top.sv
      content: "SAME\\n"
  - name: mk_b
    uses: std.CreateFile
    with:
      type: t
      filename: top.sv
      content: "SAME\\n"
  - name: publish
    uses: std.Publish
    needs: [mk_a, mk_b]
    with:
      dest: rtl
"""
    rundir, runner = _run(tmpdir, flow)
    # identical content at the same dst is not a conflict
    assert runner.status == 0
    assert os.path.isfile(os.path.join(rundir, "out", "0001", "rtl/top.sv"))
