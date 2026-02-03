"""
Test that tasks can be referenced using fragment-qualified names.

For a task in package 'a' with fragment 'b' and task 'c':
- Task is stored as a.b.c in pkg.task_m
- Should be runnable using 'b.c' (fragment-qualified)
- Should be runnable using 'a.b.c' (fully-qualified)
"""
import os
import pytest
from dv_flow.mgr import PackageLoader
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from .marker_collector import MarkerCollector


def test_task_resolution_fragment_qualified(tmpdir):
    """Test that tasks can be resolved using fragment-qualified names"""
    flow_dv = """
package:
    name: myproject
    
    tasks:
    - name: root_task
      scope: root
    
    fragments:
    - build.dv
"""
    
    build_dv = """
fragment:
    name: build
    tasks:
    - name: compile
      scope: root
      run: echo "compiling"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "build.dv"), "w") as fp:
        fp.write(build_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    assert pkg.name == "myproject"
    
    # Verify task is stored with full name
    assert "myproject.build.compile" in pkg.task_m.keys()
    
    # Now test task resolution via TaskGraphBuilder
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=tmpdir, loader=loader)
    
    # Test 1: Fully-qualified name should work
    task_node = builder.mkTaskNode("myproject.build.compile", allow_root_prefix=True)
    assert task_node is not None
    assert task_node.name == "myproject.build.compile"
    
    # Test 2: Fragment-qualified name should work (b.c format) with CLI flag
    task_node2 = builder.mkTaskNode("build.compile", allow_root_prefix=True)
    assert task_node2 is not None
    # The task will be resolved to its fully-qualified name
    assert task_node2.name == "myproject.build.compile"


def test_task_resolution_loader_exact_match_only(tmpdir):
    """Test that the loader only finds tasks with exact (fully-qualified) names"""
    flow_dv = """
package:
    name: myproject
    
    fragments:
    - build.dv
"""
    
    build_dv = """
fragment:
    name: build
    tasks:
    - name: compile
      scope: root
      run: echo "compiling"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "build.dv"), "w") as fp:
        fp.write(build_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    
    # Loader should NOT find fragment-qualified names (no automatic resolution)
    task = loader.findTask("build.compile")
    assert task is None
    
    # Loader SHOULD find fully-qualified names
    task = loader.findTask("myproject.build.compile")
    assert task is not None
    assert task.name == "myproject.build.compile"


def test_task_resolution_nested_fragments(tmpdir):
    """Test task resolution with nested fragment structure"""
    flow_dv = """
package:
    name: root
    
    fragments:
    - level1.dv
"""
    
    level1_dv = """
fragment:
    name: l1
    tasks:
    - name: task1
      scope: root
      run: echo "task1"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "level1.dv"), "w") as fp:
        fp.write(level1_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    
    # Task should be stored as root.l1.task1
    assert "root.l1.task1" in pkg.task_m.keys()
    
    # Test resolution
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=tmpdir, loader=loader)
    
    # Fragment-qualified should work with CLI flag
    task_node = builder.mkTaskNode("l1.task1", allow_root_prefix=True)
    assert task_node is not None
    
    # Fully-qualified should work
    task_node2 = builder.mkTaskNode("root.l1.task1", allow_root_prefix=True)
    assert task_node2 is not None
