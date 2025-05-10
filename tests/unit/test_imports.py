
import asyncio
import io
import json
import os
import dataclasses as dc
import pytest
from typing import Any, List, Union
import yaml
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner, task, TaskDataResult
from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from dv_flow.mgr.fileset import FileSet
from pydantic import BaseModel
from shutil import copytree

def test_pkg_path_imp(tmpdir):
    top_flow_dv = """
package:
    name: top

    imports:
    - subdir/flow.dv

    tasks:
    - name: top
      uses: subpkg.top
#      with:
#        msg: "top.top"
"""
    subpkg_flow_dv = """
package:
    name: subpkg

    tasks:
    - name: top
      uses: std.Message
      with:
        msg: "subpkg.top"
"""

    os.makedirs(os.path.join(tmpdir, "subdir"))

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(top_flow_dv)

    with open(os.path.join(tmpdir, "subdir/flow.dv"), "w") as f:
        f.write(subpkg_flow_dv)

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    print("pkg_def: %s" % str(pkg_def), flush=True)
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("top.top")
    output = asyncio.run(runner.run(task))

def test_local_name_collision(tmpdir):
    top_flow_dv = """
package:
    name: top

    imports:
    - subdir/flow.dv

    tasks:
    - name: subtask
      uses: std.Message
      with:
        msg: "top.subtask"
    - name: top
      needs: [subtask, subpkg.top]
      uses: std.Message
      with:
        msg: "top.top"
"""
    subpkg_flow_dv = """
package:
    name: subpkg

    tasks:
    - name: subtask
      uses: std.Message
      with:
        msg: "subpkg.subtask"
    - name: top
      uses: std.Message
      needs: [subtask]
      with:
        msg: "subpkg.top"
"""

    os.makedirs(os.path.join(tmpdir, "subdir"))

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(top_flow_dv)

    with open(os.path.join(tmpdir, "subdir/flow.dv"), "w") as f:
        f.write(subpkg_flow_dv)

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    print("pkg_def: %s" % str(pkg_def), flush=True)
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("top.top")
    output = asyncio.run(runner.run(task))

def test_pkg_path_imp_search(tmpdir):
    """Test that a sub-package can find a sibling relative to root project"""
    top_flow_dv = """
package:
    name: top

    imports:
    - packages/subpkg1/flow.dv

    tasks:
    - name: top
      uses: subpkg2.top
#      with:
#        msg: "top.top"
"""
    subpkg1_flow_dv = """
package:
    name: subpkg1
    imports:
    - packages/subpkg2/flow.dv

    tasks:
    - name: top
      uses: std.Message
      with:
        msg: "subpkg1.top"
"""
    subpkg2_flow_dv = """
package:
    name: subpkg2

    tasks:
    - name: top
      uses: std.Message
      with:
        msg: "subpkg2.top"
"""

    os.makedirs(os.path.join(tmpdir, "packages/subpkg1"))
    os.makedirs(os.path.join(tmpdir, "packages/subpkg2"))

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(top_flow_dv)

    with open(os.path.join(tmpdir, "packages/subpkg1/flow.dv"), "w") as f:
        f.write(subpkg1_flow_dv)
    with open(os.path.join(tmpdir, "packages/subpkg2/flow.dv"), "w") as f:
        f.write(subpkg2_flow_dv)

    def markers(marker):
        raise Exception("Marker: %s" % marker)
    pkg_def = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
    print("pkg_def: %s" % str(pkg_def), flush=True)
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("top.top")
    output = asyncio.run(runner.run(task))

def test_pkg_path_imp_search_down(tmpdir):
    """Test that a sub-package can find a sibling inside sub-directories"""
    top_flow_dv = """
package:
    name: top

    imports:
    - packages/subpkg1
    - packages/subpkg2

    tasks:
    - name: top
      uses: subpkg2.top
#      with:
#        msg: "top.top"
"""
    subpkg1_flow_dv = """
package:
    name: subpkg1

    tasks:
    - name: top
      uses: std.Message
      with:
        msg: "subpkg1.top"
"""
    subpkg2_flow_dv = """
package:
    name: subpkg2

    tasks:
    - name: top
      uses: std.Message
      with:
        msg: "subpkg2.top"
"""

    os.makedirs(os.path.join(tmpdir, "packages/subpkg1/s1"))
    os.makedirs(os.path.join(tmpdir, "packages/subpkg2/s3/s4"))

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(top_flow_dv)

    with open(os.path.join(tmpdir, "packages/subpkg1/s1/flow.dv"), "w") as f:
        f.write(subpkg1_flow_dv)
    with open(os.path.join(tmpdir, "packages/subpkg2/s3/s4/flow.dv"), "w") as f:
        f.write(subpkg2_flow_dv)

    def markers(marker):
        raise Exception("Marker: %s" % marker)
    pkg_def = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
#    print("pkg_def: %s" % str(pkg_def), flush=True)
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("top.top")
    output = asyncio.run(runner.run(task))
