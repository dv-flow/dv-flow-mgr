#****************************************************************************
#* test_show_produces.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#****************************************************************************
import json
import pytest
from dv_flow.mgr.cmds.show.collectors import ProducesCollector
from dv_flow.mgr.cmds.show.cmd_show_task import CmdShowTask
from dv_flow.mgr.cmds.show.cmd_show_tasks import CmdShowTasks


class Args:
    """Mock args for show commands."""
    def __init__(self, **kwargs):
        self.root = None
        self.param_overrides = []
        self.config = None
        self.json = False
        self.verbose = False
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_produces_collector_exact_match():
    """Test ProducesCollector with exact match."""
    collector = ProducesCollector("type=std.FileSet,filetype=verilog")
    
    class Task:
        produces = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    assert collector.matches(Task())


def test_produces_collector_subset_match():
    """Test ProducesCollector with subset match (produces has extra attributes)."""
    collector = ProducesCollector("type=std.FileSet")
    
    class Task:
        produces = [{"type": "std.FileSet", "filetype": "verilog", "vendor": "synopsys"}]
    
    assert collector.matches(Task())


def test_produces_collector_no_match():
    """Test ProducesCollector with no match."""
    collector = ProducesCollector("type=std.FileSet,filetype=vhdl")
    
    class Task:
        produces = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    assert not collector.matches(Task())


def test_produces_collector_multiple_patterns():
    """Test ProducesCollector with multiple produces patterns."""
    collector = ProducesCollector("filetype=vhdl")
    
    class Task:
        produces = [
            {"type": "std.FileSet", "filetype": "verilog"},
            {"type": "std.FileSet", "filetype": "vhdl"}
        ]
    
    # Should match because second pattern has vhdl
    assert collector.matches(Task())


def test_produces_collector_no_produces():
    """Test ProducesCollector with task that has no produces."""
    collector = ProducesCollector("type=std.FileSet")
    
    class Task:
        produces = None
    
    assert not collector.matches(Task())


def test_produces_collector_empty_produces():
    """Test ProducesCollector with task that has empty produces."""
    collector = ProducesCollector("type=std.FileSet")
    
    class Task:
        produces = []
    
    assert not collector.matches(Task())


def test_show_task_displays_produces(tmpdir, capsys):
    """Test show task displays produces."""
    flow_yaml = """
package:
  name: test_show
  tasks:
    - name: Producer
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "produce"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdShowTask()
    args = Args(name="test_show.Producer", json=True, root=str(tmpdir))
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    assert 'produces' in output
    assert output['produces'] is not None
    assert len(output['produces']) == 1
    assert output['produces'][0]['type'] == 'std.FileSet'
    assert output['produces'][0]['filetype'] == 'verilog'


def test_show_task_no_produces(tmpdir, capsys):
    """Test show task with no produces."""
    flow_yaml = """
package:
  name: test_no_produces
  tasks:
    - name: NoProducer
      run: echo "no produces"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdShowTask()
    args = Args(name="test_no_produces.NoProducer", json=True, root=str(tmpdir))
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    assert output['produces'] is None


def test_show_tasks_filter_by_produces(tmpdir, capsys):
    """Test show tasks with produces filter."""
    flow_yaml = """
package:
  name: test_filter
  tasks:
    - name: VerilogProducer
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "verilog"
    - name: VhdlProducer
      produces:
        - type: std.FileSet
          filetype: vhdl
      run: echo "vhdl"
    - name: NoProducer
      run: echo "nothing"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdShowTasks()
    args = Args(
        root=str(tmpdir),
        json=True,
        produces="type=std.FileSet,filetype=verilog"
    )
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    tasks = output['results']
    
    # Should only return VerilogProducer
    task_names = [t['name'] for t in tasks]
    assert 'test_filter.VerilogProducer' in task_names
    assert 'test_filter.VhdlProducer' not in task_names
    assert 'test_filter.NoProducer' not in task_names


def test_show_tasks_filter_by_type_only(tmpdir, capsys):
    """Test show tasks filtering by type only."""
    flow_yaml = """
package:
  name: test_type_filter
  tasks:
    - name: FileSetProducer
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "fileset"
    - name: CustomProducer
      produces:
        - type: custom.DataSet
      run: echo "custom"
    - name: NoProducer
      run: echo "nothing"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdShowTasks()
    args = Args(
        root=str(tmpdir),
        json=True,
        produces="type=std.FileSet"
    )
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    tasks = output['results']
    
    # Should return FileSetProducer but not CustomProducer or NoProducer
    task_names = [t['name'] for t in tasks]
    assert 'test_type_filter.FileSetProducer' in task_names
    assert 'test_type_filter.CustomProducer' not in task_names
    assert 'test_type_filter.NoProducer' not in task_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
