
import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from .task_listener_test import TaskListenerTest
from .marker_collector import MarkerCollector

def test_uses_name_error(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: base
    - name: task1
      uses: base_t
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    assert len(marker_collector.markers) == 1
    assert "Did you mean 'foo.base'" in marker_collector.markers[0].msg
