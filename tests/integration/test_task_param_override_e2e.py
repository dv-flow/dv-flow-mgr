"""End-to-end integration tests for task parameter overrides"""
import os
import asyncio
import pytest
from dv_flow.mgr.util import loadProjPkgDef, parse_parameter_overrides
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner


def test_e2e_task_param_override_from_docs_example(tmpdir):
    """Test the example from docs: dfm run build -D include=*.sv"""
    flow_dv = """
package:
  name: counter_project
  
  tasks:
  - name: rtl
    scope: root
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "counter.sv"
  
  - name: build
    scope: root
    uses: std.Message
    needs: [rtl]
    with:
      msg: "Building with files"
"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Create a dummy source file
    with open(os.path.join(tmpdir, "counter.sv"), "w") as fp:
        fp.write("module counter(); endmodule\n")
    
    # Parse override: change the include pattern
    overrides = parse_parameter_overrides(["include=*.v"])
    
    loader, pkg = loadProjPkgDef(str(tmpdir), parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    # Build the rtl task node
    task_node = builder.mkTaskNode("counter_project.rtl")
    
    # Verify override was applied
    assert task_node.params.include == ["*.v"]  # Changed from "counter.sv"



def test_e2e_multiple_task_params(tmpdir):
    """Test multiple parameter overrides on same task"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: files
    scope: root
    uses: std.FileSet
    with:
      type: text
      include: "*.txt"
      base: "."
"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Override both type and include
    overrides = parse_parameter_overrides(["type=source", "include=*.sv"])
    
    loader, pkg = loadProjPkgDef(str(tmpdir), parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.files")
    
    # Both overrides applied
    assert task_node.params.type == "source"
    assert task_node.params.include == ["*.sv"]



def test_e2e_qualified_vs_unqualified(tmpdir):
    """Test that qualified override takes precedence over unqualified"""
    flow_dv = """
package:
  name: myproject
  
  tasks:
  - name: task1
    scope: root
    uses: std.Message
    with:
      msg: "default1"
      
  - name: task2
    scope: root
    uses: std.Message
    with:
      msg: "default2"
"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Unqualified override will apply to both
    overrides = parse_parameter_overrides(["msg=global_override"])
    
    loader, pkg = loadProjPkgDef(str(tmpdir), parameter_overrides=overrides)
    task_overrides = overrides.get('task', {})
    leaf_overrides = overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    # Both tasks get the override
    task1 = builder.mkTaskNode("myproject.task1")
    task2 = builder.mkTaskNode("myproject.task2")
    
    assert task1.params.msg == "global_override"
    assert task2.params.msg == "global_override"



def test_e2e_inline_json_string(tmpdir):
    """Test inline JSON string with -P option"""
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
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    # Use inline JSON string instead of file
    from dv_flow.mgr.util import load_param_file
    json_string = '{"tasks": {"build": {"include": ["*.sv", "*.v"]}}}'
    file_overrides = load_param_file(json_string)
    
    cli_overrides = parse_parameter_overrides([])
    from dv_flow.mgr.util import merge_parameter_overrides
    merged_overrides = merge_parameter_overrides(cli_overrides, file_overrides)
    
    loader, pkg = loadProjPkgDef(str(tmpdir), parameter_overrides=merged_overrides)
    task_overrides = merged_overrides.get('task', {})
    leaf_overrides = merged_overrides.get('leaf', {})
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=rundir,
        loader=loader,
        task_param_overrides=task_overrides,
        leaf_param_overrides=leaf_overrides
    )
    
    task_node = builder.mkTaskNode("myproject.build")
    
    # Verify inline JSON was applied
    assert task_node.params.include == ["*.sv", "*.v"]
