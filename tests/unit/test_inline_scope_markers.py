"""
Tests for inline scope markers (root, export, local) as alternatives to name field.

This feature allows five ways to specify a task name:
1. - name: MyTask
2. - root: MyTask
3. - export: MyTask
4. - local: MyTask
5. - override: MyTask
"""
import os
import pytest
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def test_root_inline_marker(tmpdir):
    """Test that 'root: TaskName' works as alternative to 'name: TaskName' with 'scope: root'"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - root: MyRootTask
      run: echo "I am root"
    - name: RegularTask
      run: echo "I am regular"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check that root inline marker creates task with correct name and scope
    root_task = pkg_def.task_m["my_pkg.MyRootTask"]
    assert root_task.name == "my_pkg.MyRootTask"
    assert root_task.is_root == True
    assert root_task.is_export == False
    assert root_task.is_local == False
    
    regular_task = pkg_def.task_m["my_pkg.RegularTask"]
    assert regular_task.is_root == False


def test_export_inline_marker(tmpdir):
    """Test that 'export: TaskName' works as alternative to 'name: TaskName' with 'scope: export'"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - export: MyExportTask
      run: echo "I am exported"
    - name: InternalTask
      run: echo "I am internal"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check that export inline marker creates task with correct name and scope
    export_task = pkg_def.task_m["my_pkg.MyExportTask"]
    assert export_task.name == "my_pkg.MyExportTask"
    assert export_task.is_root == False
    assert export_task.is_export == True
    assert export_task.is_local == False
    
    internal_task = pkg_def.task_m["my_pkg.InternalTask"]
    assert internal_task.is_export == False


def test_local_inline_marker(tmpdir):
    """Test that 'local: TaskName' works as alternative to 'name: TaskName' with 'scope: local'"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - local: MyLocalTask
      run: echo "I am local"
    - name: PackageTask
      run: echo "I am package-scoped"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check that local inline marker creates task with correct name and scope
    local_task = pkg_def.task_m["my_pkg.MyLocalTask"]
    assert local_task.name == "my_pkg.MyLocalTask"
    assert local_task.is_root == False
    assert local_task.is_export == False
    assert local_task.is_local == True
    
    package_task = pkg_def.task_m["my_pkg.PackageTask"]
    assert package_task.is_local == False


def test_all_five_name_methods(tmpdir):
    """Test all five ways of specifying task names in one package"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: Task1
      run: echo "Named normally"
    - root: Task2
      run: echo "Root task"
    - export: Task3
      run: echo "Exported task"
    - local: Task4
      run: echo "Local task"
    - name: BaseTask
      run: echo "Base"
    - override: BaseTask
      run: echo "Override"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Verify all tasks exist with correct properties
    task1 = pkg_def.task_m["my_pkg.Task1"]
    assert task1.name == "my_pkg.Task1"
    assert not task1.is_root and not task1.is_export and not task1.is_local
    
    task2 = pkg_def.task_m["my_pkg.Task2"]
    assert task2.name == "my_pkg.Task2"
    assert task2.is_root == True
    
    task3 = pkg_def.task_m["my_pkg.Task3"]
    assert task3.name == "my_pkg.Task3"
    assert task3.is_export == True
    
    task4 = pkg_def.task_m["my_pkg.Task4"]
    assert task4.name == "my_pkg.Task4"
    assert task4.is_local == True
    
    # Override task should exist
    base_task = pkg_def.task_m["my_pkg.BaseTask"]
    assert base_task.name == "my_pkg.BaseTask"


def test_inline_marker_with_explicit_scope(tmpdir):
    """Test that inline marker can be combined with explicit scope field"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - root: RootAndExport
      scope: export
      run: echo "I am root and export"
    - export: ExportAndRoot
      scope: root
      run: echo "I am export and root"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Check that both scopes are applied
    task1 = pkg_def.task_m["my_pkg.RootAndExport"]
    assert task1.is_root == True
    assert task1.is_export == True
    
    task2 = pkg_def.task_m["my_pkg.ExportAndRoot"]
    assert task2.is_export == True
    assert task2.is_root == True


def test_multiple_name_fields_error(tmpdir):
    """Test that using multiple name fields raises validation error"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: Task1
      root: Task1
      run: echo "This should fail"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    markers = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(rundir, "flow.dv"))
    
    # Should have an error about multiple name fields
    errors = [m for m in markers.markers if str(m.severity) == "SeverityE.Error"]
    assert len(errors) > 0
    # Check that error mentions both fields
    error_msgs = [m.msg for m in errors]
    assert any("name" in msg.lower() and "root" in msg.lower() for msg in error_msgs)


def test_subtasks_with_inline_markers(tmpdir):
    """Test that inline markers work for subtasks within a task body"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: ParentTask
      tasks:
      - root: SubRoot
        run: echo "sub root"
      - export: SubExport
        run: echo "sub export"
      - local: SubLocal
        run: echo "sub local"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    parent_task = pkg_def.task_m["my_pkg.ParentTask"]
    assert len(parent_task.subtasks) == 3
    
    # Check subtasks have correct visibility
    sub_root = parent_task.subtasks[0]
    assert "SubRoot" in sub_root.name
    assert sub_root.is_root == True
    
    sub_export = parent_task.subtasks[1]
    assert "SubExport" in sub_export.name
    assert sub_export.is_export == True
    
    sub_local = parent_task.subtasks[2]
    assert "SubLocal" in sub_local.name
    assert sub_local.is_local == True


def test_inline_markers_with_uses(tmpdir):
    """Test that inline markers work with task inheritance (uses)"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: BaseTask
      run: echo "base"
    - root: RootDerived
      uses: BaseTask
      run: echo "derived"
    - export: ExportDerived
      uses: BaseTask
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    base_task = pkg_def.task_m["my_pkg.BaseTask"]
    
    root_derived = pkg_def.task_m["my_pkg.RootDerived"]
    assert root_derived.is_root == True
    assert root_derived.uses == base_task
    
    export_derived = pkg_def.task_m["my_pkg.ExportDerived"]
    assert export_derived.is_export == True
    assert export_derived.uses == base_task


def test_inline_markers_with_needs(tmpdir):
    """Test that inline markers work with task dependencies"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - export: Task1
      run: echo "task 1"
    - root: Task2
      needs: [Task1]
      run: echo "task 2"
    - local: Task3
      needs: [Task1, Task2]
      run: echo "task 3"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    task1 = pkg_def.task_m["my_pkg.Task1"]
    task2 = pkg_def.task_m["my_pkg.Task2"]
    task3 = pkg_def.task_m["my_pkg.Task3"]
    
    assert task1.is_export == True
    assert task2.is_root == True
    assert task3.is_local == True
    
    # Check dependencies
    assert task1 in task2.needs
    assert task1 in task3.needs
    assert task2 in task3.needs


def test_inline_markers_in_fragments(tmpdir):
    """Test that inline markers work in fragment files"""
    fragment = """
fragment:
    tasks:
    - root: FragmentRoot
      run: echo "fragment root"
    - export: FragmentExport
      run: echo "fragment export"
"""
    flowdv = """
package:
    name: my_pkg
    fragments:
    - fragment.yaml
    tasks:
    - name: MainTask
      run: echo "main"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "fragment.yaml"), "w") as fp:
        fp.write(fragment)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    # Fragment tasks should be loaded with correct visibility
    frag_root = pkg_def.task_m["my_pkg.FragmentRoot"]
    assert frag_root.is_root == True
    
    frag_export = pkg_def.task_m["my_pkg.FragmentExport"]
    assert frag_export.is_export == True
    
    main_task = pkg_def.task_m["my_pkg.MainTask"]
    assert not main_task.is_root and not main_task.is_export


def test_inline_markers_backward_compatibility(tmpdir):
    """Test that existing 'name' + 'scope' syntax still works"""
    flowdv = """
package:
    name: my_pkg
    tasks:
    - name: Task1
      scope: root
      run: echo "old style root"
    - name: Task2
      scope: [root, export]
      run: echo "old style multiple"
    - name: Task3
      run: echo "no scope"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    
    task1 = pkg_def.task_m["my_pkg.Task1"]
    assert task1.is_root == True
    
    task2 = pkg_def.task_m["my_pkg.Task2"]
    assert task2.is_root == True
    assert task2.is_export == True
    
    task3 = pkg_def.task_m["my_pkg.Task3"]
    assert not task3.is_root and not task3.is_export and not task3.is_local
