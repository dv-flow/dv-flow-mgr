import os
import pytest
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.task import Task
from dv_flow.mgr.package import Package
from dv_flow.mgr.package_loader import PackageLoader
from dv_flow.mgr.task_def import TaskDef, RundirE

def test_basic_var_resolution(tmpdir):
    """Test basic variable reference to package variable"""
    flow_dv = """
package:
    name: test_pkg
    with:
      pkg_var:
        type: str
        value: package_value
    tasks:
    - name: test_task
      with:
          task_var:
              type: str
              value: ${{ pkg_var }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    def marker(marker):
        raise Exception("Marker: %s" % str(marker))

    pkg = PackageLoader(marker_listeners=[marker]).load(
        os.path.join(tmpdir, "flow.dv"))

    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    assert hasattr(node.params, "task_var")
    assert getattr(node.params, "task_var") == "package_value"

def test_compound_task_var_resolution(tmpdir):
    """Test variable reference to compound task's variables via 'this'"""
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: compound_task
      with:
          compound_var:
              type: str
              value: compound_value
      body:
      - name: subtask
        with:
            subtask_var:
                type: str
                value: ${{ this.compound_var }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    def marker(marker):
        raise Exception("Marker: %s" % str(marker))

    pkg = PackageLoader(marker_listeners=[marker]).load(
        os.path.join(tmpdir, "flow.dv"))

    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.compound_task")

    assert len(node.tasks) == 2
    subtask_node = node.tasks[1]
    assert hasattr(subtask_node.params, "subtask_var")
    assert getattr(subtask_node.params, "subtask_var") == "compound_value"

def test_package_qualified_var_resolution(tmpdir):
    """Test package-qualified variable reference"""
    pkg1_dv = """
package:
    name: pkg1
    with:
        var:
            type: str
            value: pkg1_value
"""
    flow_dv = """
package:
    name: pkg2
    imports:
    - pkg1.dv
    tasks:
    - name: test_task
      with:
          task_var:
              type: str
              value: ${{ pkg1.var }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    with open(os.path.join(tmpdir, "pkg1.dv"), "w") as f:
        f.write(pkg1_dv)

    def marker(marker):
        raise Exception("Marker: %s" % str(marker))

    pkg = PackageLoader(marker_listeners=[marker]).load(
        os.path.join(tmpdir, "flow.dv"))

    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("pkg2.test_task")

    assert hasattr(node.params, "task_var")
    assert getattr(node.params, "task_var") == "pkg1_value"

def test_compound_task_scoping(tmpdir):
    """Test multi-level compound task variable scoping"""
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: outer_task
      with:
          outer_var:
              type: str
              value: outer_value
      body:
      - name: inner_task
        with:
            inner_var:
                type: str
                value: ${{ this.outer_var }}
        body:
        - name: leaf_task
          with:
              leaf_var:
                  type: str
                  value: ${{ this.inner_var }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    def marker(marker):
        raise Exception("Marker: %s" % str(marker))

    pkg = PackageLoader(marker_listeners=[marker]).load(
        os.path.join(tmpdir, "flow.dv"))

    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.outer_task")

    assert len(node.tasks) == 2  # inner_task
    inner_node = node.tasks[-1]
    assert len(inner_node.tasks) == 2  # leaf_task 
    leaf_node = inner_node.tasks[-1]

    assert hasattr(leaf_node.params, "leaf_var")
    assert getattr(leaf_node.params, "leaf_var") == "outer_value"
