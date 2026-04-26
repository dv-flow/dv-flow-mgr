"""Tests for config-level task overrides (Phase 2)."""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef
from .marker_collector import MarkerCollector


def test_override_leaf_task(tmp_path, capsys):
    """Config overrides a top-level leaf task with std.Null."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "should_not_appear"
    - name: entry
      uses: std.Message
      needs: [expensive]
      with:
        msg: "entry_msg"
    configs:
    - name: fast
      overrides:
      - task: pkg.expensive
        with: std.Null
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="fast")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "should_not_appear" not in captured.out
    assert "entry_msg" in captured.out


def test_override_nested_compound(tmp_path, capsys):
    """Override a task two levels deep (pkg.Outer.Inner.Sub)."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: Outer
      body:
      - name: Inner
        body:
        - name: Sub
          uses: std.Message
          with:
            msg: "deep_msg"
      - name: After
        uses: std.Message
        needs: [Inner]
        with:
          msg: "after_msg"
    - name: entry
      passthrough: all
      consumes: none
      needs: [Outer]
    configs:
    - name: fast
      overrides:
      - task: pkg.Outer.Inner.Sub
        with: std.Null
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="fast")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "deep_msg" not in captured.out
    assert "after_msg" in captured.out


def test_override_config_inheritance(tmp_path, capsys):
    """Config A uses config B.  Both have overrides.  B's apply first, A's shadow."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "t1_original"
    - name: t2
      uses: std.Message
      with:
        msg: "t2_original"
    - name: t1_repl
      uses: std.Message
      with:
        msg: "t1_replaced"
    - name: entry
      uses: std.Message
      needs: [t1, t2]
      with:
        msg: "entry_msg"
    configs:
    - name: base_cfg
      overrides:
      - task: pkg.t1
        with: pkg.t1_repl
      - task: pkg.t2
        with: std.Null
    - name: derived_cfg
      uses: base_cfg
      overrides:
      - task: pkg.t1
        with: std.Null
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="derived_cfg")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    # derived_cfg overrides t1 with std.Null (shadows base_cfg's t1_repl)
    assert "t1_original" not in captured.out
    assert "t1_replaced" not in captured.out
    # base_cfg overrides t2 with std.Null (inherited, not shadowed)
    assert "t2_original" not in captured.out
    assert "entry_msg" in captured.out


def test_override_preserves_needs(tmp_path, capsys):
    """Overridden task sits in the correct DAG position; downstream tasks
    that need the original still resolve correctly."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: producer
      uses: std.Message
      with:
        msg: "producer_msg"
    - name: consumer
      uses: std.Message
      needs: [producer]
      with:
        msg: "consumer_msg"
    - name: entry
      passthrough: all
      consumes: none
      needs: [consumer]
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    builder.addOverride("pkg.producer", "std.Null")
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    # producer was replaced with std.Null -- should not print
    assert "producer_msg" not in captured.out
    # consumer still runs (its need on producer resolves to the Null node)
    assert "consumer_msg" in captured.out


def test_override_inline_task(tmp_path):
    """Package-level override with an inline task definition (dict value)."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    overrides:
      pkg.expensive:
        shell: bash
        run: "echo inline_replacement"
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "should_not_appear"
    - name: entry
      passthrough: all
      consumes: none
      needs: [expensive]
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    # Verify the synthetic task was created
    assert "pkg._override_0" in pkg.task_m
    assert pkg.substitution_m["pkg.expensive"] == "pkg._override_0"
    # Verify the graph builds and runs
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0


def test_override_compound_subtask(tmp_path, capsys):
    """Config overrides a subtask inside a compound body."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: Compound
      body:
      - name: Step1
        uses: std.Message
        with:
          msg: "step1_msg"
      - name: Step2
        uses: std.Message
        needs: [Step1]
        with:
          msg: "step2_msg"
    - name: entry
      passthrough: all
      consumes: none
      needs: [Compound]
    configs:
    - name: fast
      overrides:
      - task: pkg.Compound.Step1
        with: std.Null
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="fast")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "step1_msg" not in captured.out
    assert "step2_msg" in captured.out


def test_override_missing_replacement(tmp_path):
    """Override references a non-existent replacement task."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: entry
      uses: std.Message
      with:
        msg: hello
    configs:
    - name: fast
      overrides:
      - task: pkg.entry
        with: pkg.DoesNotExist
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="fast")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    with pytest.raises(Exception, match="replacement task not found"):
        builder.mkTaskNode("pkg.entry")


def test_override_package_level(tmp_path, capsys):
    """Package-level overrides: dict (not config)."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    overrides:
      pkg.expensive: std.Null
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "should_not_appear"
    - name: entry
      uses: std.Message
      needs: [expensive]
      with:
        msg: "entry_msg"
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "should_not_appear" not in captured.out
    assert "entry_msg" in captured.out


def test_override_precedence(tmp_path, capsys):
    """Both package-level and config-level override the same task. Config wins."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    overrides:
      pkg.target: std.Null
    tasks:
    - name: target
      uses: std.Message
      with:
        msg: "should_not_appear"
    - name: replacement
      uses: std.Message
      with:
        msg: "config_replacement"
    - name: entry
      uses: std.Message
      needs: [target]
      with:
        msg: "entry_msg"
    configs:
    - name: cfg
      overrides:
      - task: pkg.target
        with: pkg.replacement
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="cfg")
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    # Config override should win: replacement task runs, not Null
    assert "config_replacement" in captured.out
    assert "should_not_appear" not in captured.out


def test_no_override_without_config(tmp_path, capsys):
    """Same YAML without -c fast. Original tasks run."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "expensive_output"
    - name: entry
      uses: std.Message
      needs: [expensive]
      with:
        msg: "entry_msg"
    configs:
    - name: fast
      overrides:
      - task: pkg.expensive
        with: std.Null
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    # No config selected, so override should NOT apply
    assert "expensive_output" in captured.out
    assert "entry_msg" in captured.out


def test_override_addoverride_api(tmp_path, capsys):
    """Test addOverride API directly on the builder."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: expensive
      uses: std.Message
      with:
        msg: "should_not_appear"
    - name: entry
      uses: std.Message
      needs: [expensive]
      with:
        msg: "entry_msg"
""")
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        str(tmp_path / "flow.dv"))
    assert len(collector.markers) == 0
    rundir = str(tmp_path / "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    builder.addOverride("pkg.expensive", "std.Null")
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode("pkg.entry")
    output = asyncio.run(runner.run(node))
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "should_not_appear" not in captured.out
    assert "entry_msg" in captured.out
