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
from .marker_collector import MarkerCollector

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

    # f2 feeds f1: f1 depends on f2, so f1's output includes f2's FileSet (via passthrough=All) + its own
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

    # f2 feeds f1 (cross-package): f1 depends on f2, output includes both FileSets (passthrough=All)
    assert len(out.output) == 2

def test_feeds_3(tmpdir):
    flow_dv = """
package:
    name: p1
    imports:
    - pkg2.dv

    tasks:
    - name: fx
      uses: std.FileSet

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
      feeds: [p1.fx]
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

    assert len(out.output) == 1
def test_feeds_fragment_qualified(tmpdir):
    """Test that feeds can reference tasks using fragment-qualified names (e.g. sim.smoke-sim)"""
    flow_dv = """
package:
    name: p1

    tasks:
    - name: feeder
      uses: std.FileSet
      feeds: [sim.smoke-sim]
      with:
        include: file2.txt

    fragments:
    - frag.dv
"""

    frag_dv = """
fragment:
    name: sim

    tasks:
    - name: smoke-sim
      uses: std.FileSet
      with:
        include: file1.txt
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    with open(os.path.join(tmpdir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)

    with open(os.path.join(tmpdir, "file1.txt"), "w") as fp:
        fp.write("file1")

    with open(os.path.join(tmpdir, "file2.txt"), "w") as fp:
        fp.write("file2")

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[marker_collector]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(marker_collector.markers) == 0, \
        f"Unexpected markers: {[m.msg for m in marker_collector.markers]}"

    builder = TaskGraphBuilder(pkg_def, os.path.join(tmpdir, "rundir"))
    smoke_sim_task = builder.mkTaskNode("p1.sim.smoke-sim")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(smoke_sim_task))
    assert runner.status == 0
    assert out.changed == True

def test_config_feeds_establishes_dependency(tmpdir):
    """Test that a config's task with feeds: properly becomes a dependency of the fed task.

    This is the 'dfm run -c debug sim.smoke-sim' scenario: the debug config injects
    a task that provides debug defines to the simulation task via feeds.
    Currently fails because the feeds are collected but never applied to task.needs.
    """
    flow_dv = """
package:
    name: p1

    tasks:
    - name: smoke-sim
      uses: std.FileSet
      with:
        include: file1.txt

    configs:
    - name: debug
      tasks:
      - name: SimDebugOptions
        uses: std.FileSet
        feeds: [smoke-sim]
        with:
          include: file2.txt
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    with open(os.path.join(tmpdir, "file1.txt"), "w") as fp:
        fp.write("file1")

    with open(os.path.join(tmpdir, "file2.txt"), "w") as fp:
        fp.write("file2")

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[marker_collector]).load(
        os.path.join(tmpdir, "flow.dv"), config='debug')

    assert len(marker_collector.markers) == 0, \
        f"Unexpected markers: {[m.msg for m in marker_collector.markers]}"

    smoke_sim_task = pkg_def.task_m.get('p1.smoke-sim')
    assert smoke_sim_task is not None

    debug_opts_task = pkg_def.task_m.get('p1.SimDebugOptions')
    assert debug_opts_task is not None

    # Core assertion: feeds must have established this dependency
    assert debug_opts_task in smoke_sim_task.needs, \
        f"feeds: [smoke-sim] did not add SimDebugOptions to smoke-sim.needs. " \
        f"Got needs: {[n.name for n in smoke_sim_task.needs]}"
