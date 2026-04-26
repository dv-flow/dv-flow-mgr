"""Tests for std.Null task (Phase 3)."""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from .marker_collector import MarkerCollector


def test_null_produces_no_output(tmpdir):
    """std.Null with no inputs produces empty output."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: entry
      uses: std.Null
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    assert len(output.output) == 0


def test_null_passthrough(tmpdir):
    """std.Null with passthrough: all passes its inputs through."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: create_file
      uses: std.CreateFile
      with:
        filename: hello.txt
        content: "hello"
    - name: null_step
      uses: std.Null
      passthrough: all
      needs: [create_file]
    - name: entry
      passthrough: all
      consumes: none
      needs: [null_step]
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    # The file from create_file should pass through std.Null
    assert len(output.output) >= 1


def test_null_as_override(tmpdir, capsys):
    """std.Null used as an override replacement; task graph completes."""
    flow_dv = """\
package:
    name: pkg
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "should not appear"
    - name: entry
      uses: std.Message
      needs: [expensive]
      with:
        msg: "entry_msg"
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), "flow.dv"))
    assert len(collector.markers) == 0

    rundir = os.path.join(str(tmpdir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    # Override expensive with std.Null
    builder.addOverride("pkg.expensive", "std.Null")
    runner = TaskSetRunner(rundir=rundir)

    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    # The expensive task should NOT have run
    assert "should not appear" not in captured.out
    # The entry task should still run
    assert "entry_msg" in captured.out
