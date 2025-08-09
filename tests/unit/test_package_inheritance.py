import asyncio
import json
import os
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: p1
    imports:
    - pbase.dv
    tasks:
    
"""