import os
import pytest
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector

def test_invalid_field_in_task_def(tmpdir):
    """Test that TaskDef rejects unknown fields and suggests similar valid fields"""
    flow_dv = """
package:
    name: test-pkg

    tasks:
    - name: task1
      type: some_type
      run: echo "test"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    
    # Should have caught the validation error
    assert len(marker_collector.markers) > 0
    # Check that error mentions the invalid field 'type'
    error_msg = marker_collector.markers[0].msg
    assert "type" in error_msg.lower()
    # Should suggest 'uses' as a similar field
    assert "uses" in error_msg.lower()

def test_another_typo_field(tmpdir):
    """Test that TaskDef catches typos in field names"""
    flow_dv = """
package:
    name: test-pkg

    tasks:
    - name: task1
      descr: "A task with a typo"
      run: echo "test"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    
    # Should have caught the validation error
    assert len(marker_collector.markers) > 0
    error_msg = marker_collector.markers[0].msg
    # Check that error mentions the invalid field 'descr'
    assert "descr" in error_msg.lower()
    # Should suggest 'desc' as a similar field
    assert "desc" in error_msg.lower()
