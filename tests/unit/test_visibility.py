"""
Tests for task visibility scope feature.

Task visibility controls:
- root: Task is executable from CLI (shows in task listing)
- export: Task is visible outside the package
- local: Task is only visible within its declaration fragment
- no scope: Task is visible within the package (default)
"""
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from .marker_collector import MarkerCollector


def test_root_scope_filtering(tmpdir):
    """Test that only root tasks are shown in command listing"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: entry
      scope: root
      desc: "Entry point task"
    - name: helper
      desc: "Helper task (not root)"
    - name: build
      scope: [root, export]
      desc: "Build task"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check visibility flags
    entry_task = pkg_def.task_m["my_pkg.entry"]
    assert entry_task.is_root == True
    assert entry_task.is_export == False
    assert entry_task.is_local == False
    
    helper_task = pkg_def.task_m["my_pkg.helper"]
    assert helper_task.is_root == False
    assert helper_task.is_export == False
    assert helper_task.is_local == False
    
    build_task = pkg_def.task_m["my_pkg.build"]
    assert build_task.is_root == True
    assert build_task.is_export == True
    assert build_task.is_local == False


def test_export_scope_visibility(tmpdir):
    """Test that export tasks are visible across packages"""
    pkg1 = """
package:
    name: pkg1
    tasks:
    - name: public_task
      scope: export
      run: echo "public"
    - name: internal_task
      run: echo "internal"
"""
    pkg2 = """
package:
    name: pkg2
    imports:
    - pkg1.yaml
    tasks:
    - name: use_public
      needs:
      - pkg1.public_task
      run: echo "using public"
    - name: use_internal
      needs:
      - pkg1.internal_task
      run: echo "using internal"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "pkg1.yaml"), "w") as fp:
        fp.write(pkg1)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(pkg2)
    
    markers = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(rundir, "flow.dv"))
    
    # Check that public_task is marked as export
    public_task = pkg_def.pkg_m["pkg1"].task_m["pkg1.public_task"]
    assert public_task.is_export == True
    
    internal_task = pkg_def.pkg_m["pkg1"].task_m["pkg1.internal_task"]
    assert internal_task.is_export == False
    
    # Check that we got a warning for referencing non-export task
    warnings = [m for m in markers.markers if str(m.severity) == "SeverityE.Warning"]
    assert len(warnings) == 1
    assert "pkg1.internal_task" in warnings[0].msg
    assert "not marked 'export'" in warnings[0].msg


def test_local_scope_visibility(tmpdir):
    """Test that local tasks are only visible within their fragment"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: global_task
      run: echo "global"
    - name: parent
      body:
      - name: local_subtask
        scope: local
        run: echo "local"
      - name: use_local
        needs:
        - local_subtask
        run: echo "using local"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check that local subtask has local flag
    parent_task = pkg_def.task_m["my_pkg.parent"]
    local_task = None
    for subtask in parent_task.subtasks:
        if subtask.name == "my_pkg.parent.local_subtask":
            local_task = subtask
            break
    
    assert local_task is not None
    assert local_task.is_local == True
    assert local_task.is_root == False
    assert local_task.is_export == False


def test_scope_as_string(tmpdir):
    """Test that scope can be specified as a single string"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: task1
      scope: root
      run: echo "task1"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    task1 = pkg_def.task_m["my_pkg.task1"]
    assert task1.is_root == True


def test_scope_as_list(tmpdir):
    """Test that scope can be specified as a list"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: task1
      scope: [root, export]
      run: echo "task1"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    task1 = pkg_def.task_m["my_pkg.task1"]
    assert task1.is_root == True
    assert task1.is_export == True


def test_no_scope_default(tmpdir):
    """Test that tasks without scope are visible within package"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: task1
      run: echo "task1"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    task1 = pkg_def.task_m["my_pkg.task1"]
    # Default is package-visible (no special flags)
    assert task1.is_root == False
    assert task1.is_export == False
    assert task1.is_local == False


def test_task_execution_not_affected(tmpdir):
    """Test that tasks can still be executed regardless of visibility"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: root_task
      scope: root
      run: echo "root"
    - name: internal_task
      run: echo "internal"
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, os.getcwd())
    
    # Both tasks should be executable
    root_task = builder.mkTaskNode("my_pkg.root_task")
    assert root_task is not None
    
    internal_task = builder.mkTaskNode("my_pkg.internal_task")
    assert internal_task is not None
