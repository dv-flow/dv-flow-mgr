"""
Integration tests for CLI task resolution with fragment-qualified names.

This tests that 'dfm run' correctly resolves tasks using:
- Fully-qualified names (package.fragment.task)
- Fragment-qualified names (fragment.task)
- Simple names (task) when no dot is present
"""
import os
import asyncio
from dv_flow.mgr import PackageLoader
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner
from .marker_collector import MarkerCollector


def test_cli_run_with_fragment_qualified_name(tmpdir):
    """Test that CLI can run tasks using fragment-qualified names"""
    flow_dv = """
package:
    name: myapp
    
    tasks:
    - name: main
      scope: root
      run: echo "Main task"
    
    fragments:
    - tools.dv
"""
    
    tools_dv = """
fragment:
    name: build
    
    tasks:
    - name: compile
      scope: root
      run: echo "Compiling"
      
    - name: link
      scope: root
      needs: [compile]
      run: echo "Linking"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "tools.dv"), "w") as fp:
        fp.write(tools_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    
    # Verify tasks are stored with fully-qualified names
    assert "myapp.main" in pkg.task_m.keys()
    assert "myapp.build.compile" in pkg.task_m.keys()
    assert "myapp.build.link" in pkg.task_m.keys()
    
    # Test 1: Fragment-qualified name resolution (CLI usage)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=tmpdir, loader=loader)
    task_node = builder.mkTaskNode("build.compile", allow_root_prefix=True)
    assert task_node is not None
    assert task_node.name == "myapp.build.compile"
    
    # Test 2: Fully-qualified name resolution
    task_node2 = builder.mkTaskNode("myapp.build.link", allow_root_prefix=True)
    assert task_node2 is not None
    assert task_node2.name == "myapp.build.link"
    
    # Test 3: Simple name with package prefix (existing behavior)
    task_node3 = builder.mkTaskNode("myapp.main", allow_root_prefix=True)
    assert task_node3 is not None
    assert task_node3.name == "myapp.main"


def test_cli_run_respects_needs_with_fragment_names(tmpdir):
    """Test that tasks with fragment-qualified needs work correctly"""
    flow_dv = """
package:
    name: project
    
    fragments:
    - steps.dv
"""
    
    steps_dv = """
fragment:
    name: ci
    
    tasks:
    - name: build
      scope: root
      run: echo "Building"
      
    - name: test
      scope: root
      needs: [build]
      run: echo "Testing"
      
    - name: deploy
      scope: root
      needs: [test]
      run: echo "Deploying"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "steps.dv"), "w") as fp:
        fp.write(steps_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    
    # Build task graph using fragment-qualified name (CLI usage)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=tmpdir, loader=loader)
    
    # Run the deploy task which should trigger build -> test -> deploy
    task_node = builder.mkTaskNode("ci.deploy", allow_root_prefix=True)
    assert task_node is not None
    
    # Verify the dependency chain
    # The deploy task should have test as a dependency
    test_task = pkg.task_m["project.ci.test"]
    deploy_task = pkg.task_m["project.ci.deploy"]
    
    # Check that needs are resolved correctly
    assert len(deploy_task.needs) == 1
    assert deploy_task.needs[0].name == "project.ci.test"
    
    assert len(test_task.needs) == 1
    assert test_task.needs[0].name == "project.ci.build"


def test_multiple_fragments_with_same_task_names(tmpdir):
    """Test that tasks in different fragments can have the same names"""
    flow_dv = """
package:
    name: multiapp
    
    fragments:
    - frontend.dv
    - backend.dv
"""
    
    frontend_dv = """
fragment:
    name: frontend
    
    tasks:
    - name: build
      scope: root
      run: echo "Building frontend"
      
    - name: test
      scope: root
      run: echo "Testing frontend"
"""
    
    backend_dv = """
fragment:
    name: backend
    
    tasks:
    - name: build
      scope: root
      run: echo "Building backend"
      
    - name: test
      scope: root
      run: echo "Testing backend"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frontend.dv"), "w") as fp:
        fp.write(frontend_dv)
    with open(os.path.join(rundir, "backend.dv"), "w") as fp:
        fp.write(backend_dv)
    
    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    
    # Verify all tasks exist with their fragment-qualified names
    assert "multiapp.frontend.build" in pkg.task_m.keys()
    assert "multiapp.frontend.test" in pkg.task_m.keys()
    assert "multiapp.backend.build" in pkg.task_m.keys()
    assert "multiapp.backend.test" in pkg.task_m.keys()
    
    # Test that we can resolve each task individually (CLI usage)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=tmpdir, loader=loader)
    
    fe_build = builder.mkTaskNode("frontend.build", allow_root_prefix=True)
    assert fe_build is not None
    assert fe_build.name == "multiapp.frontend.build"
    
    be_build = builder.mkTaskNode("backend.build", allow_root_prefix=True)
    assert be_build is not None
    assert be_build.name == "multiapp.backend.build"
    
    fe_test = builder.mkTaskNode("frontend.test", allow_root_prefix=True)
    assert fe_test is not None
    assert fe_test.name == "multiapp.frontend.test"
    
    be_test = builder.mkTaskNode("backend.test", allow_root_prefix=True)
    assert be_test is not None
    assert be_test.name == "multiapp.backend.test"
