import os
import pytest
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector

def test_fragment_with_name(tmpdir):
    """Test that fragments can have a 'name' field and tasks are prefixed correctly"""
    flow_dv = """
package:
    name: foo
    
    tasks:
    - name: t1
    
    fragments:
    - frag.dv
"""
    
    frag_dv = """
fragment:
    name: myfrag
    tasks:
    - name: t2
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    assert pkg.name == "foo"
    assert len(pkg.task_m) == 2
    # Task from package itself
    assert "foo.t1" in pkg.task_m.keys()
    # Task from fragment with name should be foo.myfrag.t2
    assert "foo.myfrag.t2" in pkg.task_m.keys()

def test_fragment_without_name(tmpdir):
    """Test that fragments without 'name' work as before (tasks prefixed with package name only)"""
    flow_dv = """
package:
    name: foo
    
    tasks:
    - name: t1
    
    fragments:
    - frag.dv
"""
    
    frag_dv = """
fragment:
    tasks:
    - name: t2
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    assert pkg.name == "foo"
    assert len(pkg.task_m) == 2
    assert "foo.t1" in pkg.task_m.keys()
    # Task from fragment without name should be foo.t2
    assert "foo.t2" in pkg.task_m.keys()

def test_fragment_relative_qualified_name(tmpdir):
    """Test that relative qualified names can be referenced in fragments and package"""
    flow_dv = """
package:
    name: foo
    
    tasks:
    - name: t1
      needs: [myfrag.t2]
    
    fragments:
    - frag.dv
"""
    
    frag_dv = """
fragment:
    name: myfrag
    tasks:
    - name: t2
    - name: t3
      needs: [t2]
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0
    assert pkg is not None
    assert len(pkg.task_m) == 3
    
    t1 = pkg.task_m["foo.t1"]
    t2 = pkg.task_m["foo.myfrag.t2"]
    t3 = pkg.task_m["foo.myfrag.t3"]
    
    # t1 should depend on t2 using relative qualified name
    assert len(t1.needs) == 1
    assert t1.needs[0].name == "foo.myfrag.t2"
    
    # t3 should depend on t2 using relative unqualified name within fragment
    assert len(t3.needs) == 1
    assert t3.needs[0].name == "foo.myfrag.t2"

def test_fragment_name_collision(tmpdir):
    """Test that name collisions are detected"""
    flow_dv = """
package:
    name: foo
    
    tasks:
    - name: t1
    
    fragments:
    - frag1.dv
    - frag2.dv
"""
    
    frag1_dv = """
fragment:
    name: myfrag
    tasks:
    - name: t2
"""
    
    frag2_dv = """
fragment:
    name: myfrag
    tasks:
    - name: t3
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag1.dv"), "w") as fp:
        fp.write(frag1_dv)
    with open(os.path.join(rundir, "frag2.dv"), "w") as fp:
        fp.write(frag2_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    # Should have an error marker about duplicate fragment name
    assert len(marker_collector.markers) > 0
    error_found = False
    for marker in marker_collector.markers:
        if "myfrag" in marker.msg.lower() or "duplicate" in marker.msg.lower() or "collision" in marker.msg.lower():
            error_found = True
            break
    assert error_found, f"Expected error about duplicate fragment name, got: {[m.msg for m in marker_collector.markers]}"

def test_fragment_strict_parsing(tmpdir):
    """Test that fragments use strict parsing and reject unrecognized entities"""
    flow_dv = """
package:
    name: foo
    
    fragments:
    - frag.dv
"""
    
    frag_dv = """
fragment:
    name: myfrag
    tasks:
    - name: t1
    unknown_field: value
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    # Should have an error marker about unknown field
    assert len(marker_collector.markers) > 0
    error_found = False
    for marker in marker_collector.markers:
        if "unknown" in marker.msg.lower() or "extra" in marker.msg.lower():
            error_found = True
            break
    assert error_found, f"Expected error about unknown field, got: {[m.msg for m in marker_collector.markers]}"

def test_package_strict_parsing(tmpdir):
    """Test that packages also use strict parsing and reject unrecognized entities"""
    flow_dv = """
package:
    name: foo
    tasks:
    - name: t1
    unknown_field: value
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))
    
    # Should have an error marker about unknown field
    assert len(marker_collector.markers) > 0
    error_found = False
    for marker in marker_collector.markers:
        if "unknown" in marker.msg.lower() or "extra" in marker.msg.lower():
            error_found = True
            break
    assert error_found, f"Expected error about unknown field, got: {[m.msg for m in marker_collector.markers]}"
