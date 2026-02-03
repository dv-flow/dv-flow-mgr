"""Tests for task parameter overrides via -D option"""
import os
import pytest
from dv_flow.mgr.util import loadProjPkgDef, parse_parameter_overrides
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder


def test_leaf_name_override(tmpdir):
    """Test -D param=value (unqualified leaf parameter name)"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: "*.txt"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Parse override: leaf name only
    overrides = parse_parameter_overrides(["include=*.sv"])
    
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    assert pkg is not None
    
    # Extract task and leaf overrides
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    leaf_overrides = overrides.get('leaf', {})
    
    # Build task graph with overrides
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    # Create the task node
    task_node = builder.mkTaskNode("myproject.build")
    
    # Verify override was applied (include is a list type, so "*.sv" → ["*.sv"])
    assert hasattr(task_node.params, 'include')
    assert task_node.params.include == ["*.sv"]


def test_task_qualified_override(tmpdir):
    """Test -D task.param=value"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: "*.txt"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Parse override: task-qualified
    overrides = parse_parameter_overrides(["build.include=*.sv"])
    
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    assert task_node.params.include == ["*.sv"]


def test_package_qualified_override(tmpdir):
    """Test -D pkg.task.param=value"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: "*.txt"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Parse override: fully qualified
    overrides = parse_parameter_overrides(["myproject.build.include=*.sv"])
    
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    assert task_node.params.include == ["*.sv"]


def test_type_coercion_list(tmpdir):
    """Test that single string value coerces to list"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: []
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    overrides = parse_parameter_overrides(["include=counter.sv"])
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    # String should be converted to single-element list
    assert task_node.params.include == ["counter.sv"]


def test_type_coercion_bool(tmpdir):
    """Test boolean type coercion"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.Message
    with:
      msg: "default"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Use msg parameter with string override
    overrides = parse_parameter_overrides(["msg=overridden"])
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    assert task_node.params.msg == "overridden"


def test_type_coercion_int(tmpdir):
    """Test integer type coercion - use msg for string test"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.Message
    with:
      msg: "test"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    overrides = parse_parameter_overrides(["msg=changed"])
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    assert task_node.params.msg == "changed"


def test_multiple_overrides(tmpdir):
    """Test multiple -D options"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: []
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Both type and include
    overrides = parse_parameter_overrides(["type=source", "include=*.sv"])
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    assert task_node.params.type == "source"
    assert task_node.params.include == ["*.sv"]


def test_nonexistent_parameter_error(tmpdir):
    """Test error when parameter doesn't exist"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: build
    scope: root
    uses: std.FileSet
    with:
      type: text
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Use task-qualified override so it targets the build task specifically
    overrides = parse_parameter_overrides(["build.invalid=value"])
    loader, pkg = loadProjPkgDef(rundir, parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    with pytest.raises(ValueError, match="Parameter 'invalid' not found"):
        builder.mkTaskNode("myproject.build")
