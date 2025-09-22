import asyncio
import io
import json
import os
import dataclasses as dc
import pytest
from typing import Any, List, Union
import yaml
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner, task, TaskDataResult
from dv_flow.mgr.fileset import FileSet
from pydantic import BaseModel
from shutil import copytree

def test_fileset_1(tmpdir):
    """"""
    datadir = os.path.join(os.path.dirname(__file__), "data/fileset")

    copytree(
        os.path.join(datadir, "test1"), 
        os.path.join(tmpdir, "test1"))
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert runner.status == 0
    assert out.changed == True

    # Now, re-run using the same run directory.
    # Since the files haven't changed, the output must indicate that
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert out.changed == False

    # Now, add a file
    with open(os.path.join(tmpdir, "test1", "files1", "file1_3.sv"), "w") as f:
        f.write("// file1_3.sv\n")

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert out.changed == True

def test_fileset_input_1(tmpdir):
    """"""
    datadir = os.path.join(os.path.dirname(__file__), "data/fileset")

    copytree(
        os.path.join(datadir, "test1"), 
        os.path.join(tmpdir, "test1"))

    class ConsumeFilesParams(BaseModel):
        files : Union[str,List[Any]] = """
        ${{ in | jq('[ .[] | select(.type == "std.FileSet") ]') }}
        """

    @task(ConsumeFilesParams)
    async def consume_files(runner, input) -> TaskDataResult:
        print("consume_files: %s (%s)" % (str(input.params.files), str(type(input.params.files))))

        fs_l = json.loads(input.params.files)
        fs = FileSet(**(fs_l[0]))

        return TaskDataResult(
            output=[fs]
        )
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    files1 = builder.mkTaskNode("test1.files1")
    cfiles = consume_files(builder, srcdir="srcdir", needs=[files1])

    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(cfiles))

def test_glob_sys(tmpdir):
    flow_dv = """
package:
  name: p1

  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      incdirs: ["srcdir"]
"""

    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "top.sv"), "w") as fp:
        fp.write("\n")
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("p1.glob")
    output = asyncio.run(runner.run(task))

    print("output: %s" % str(output))

    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.files) == 1
    assert fs.files[0] == "top.sv"

def test_fileset_base_absolute(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    abs_base = os.path.join(rundir, "absdir")
    os.makedirs(abs_base)
    with open(os.path.join(abs_base, "file.sv"), "w") as fp:
        fp.write("// abs file\n")
    flow_dv = f'''
package:
  name: abs_pkg
  tasks:
  - name: abs
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{abs_base}"
      include: "*.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("abs_pkg.abs")
    output = asyncio.run(runner.run(task))
    fs = output.output[0]
    assert len(fs.files) == 1
    assert fs.files[0] == "file.sv"

def test_fileset_base_glob_single(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    glob_base = os.path.join(rundir, "globdir")
    os.makedirs(glob_base)
    with open(os.path.join(glob_base, "leaf"), "w") as fp:
        fp.write("// leaf file\n")
    flow_dv = f'''
package:
  name: glob_pkg
  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{rundir}/glob*/leaf"
      include: ""
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("glob_pkg.glob")
    output = asyncio.run(runner.run(task))
    fs = output.output[0]
    assert fs.basedir.endswith("leaf")

def test_fileset_base_glob_multiple(tmpdir, caplog):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    for i in range(2):
        glob_base = os.path.join(rundir, f"globdir{i}")
        os.makedirs(glob_base)
        with open(os.path.join(glob_base, "leaf"), "w") as fp:
            fp.write("// leaf file\n")
    flow_dv = f'''
package:
  name: glob_pkg
  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{rundir}/globdir*/leaf"
      include: ""
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("glob_pkg.glob")
    with caplog.at_level("ERROR"):
        output = asyncio.run(runner.run(task))
    assert runner.status != 0
    assert any("Multiple directories match glob pattern" in r.message for r in caplog.records)
