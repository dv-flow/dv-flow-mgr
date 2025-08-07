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

def test_feeds_1(tmpdir):
    flow_dv = """
package:
    name: p1

    tasks:
    - name: f1
      uses: std.FileSet
      with:
        include: file1.txt
    - name: f2
      uses: std.FileSet
      feeds: [f1]
      with:
        include: file2.txt
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    with open(os.path.join(tmpdir, "file1.txt"), "w") as fp:
        fp.write("file1")

    with open(os.path.join(tmpdir, "file2.txt"), "w") as fp:
        fp.write("file2")

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("p1.f1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert runner.status == 0
    assert out.changed == True

    assert len(out.output) == 2

def test_feeds_2(tmpdir):
    flow_dv = """
package:
    name: p1
    imports:
    - pkg2.dv

    tasks:
    - name: f1
      uses: std.FileSet
      with:
        include: file1.txt
"""

    pkg2_dv = """
package:
    name: p2

    tasks:
    - name: f2
      uses: std.FileSet
      feeds: [p1.f1]
      with:
        include: file2.txt
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    with open(os.path.join(tmpdir, "pkg2.dv"), "w") as fp:
        fp.write(pkg2_dv)

    with open(os.path.join(tmpdir, "file1.txt"), "w") as fp:
        fp.write("file1")

    with open(os.path.join(tmpdir, "file2.txt"), "w") as fp:
        fp.write("file2")

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("p1.f1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert runner.status == 0
    assert out.changed == True

    assert len(out.output) == 2