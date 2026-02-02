#****************************************************************************
#* test_produces_validation.py
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
import os
import json
import pytest
from dv_flow.mgr.cmds.cmd_validate import CmdValidate


class Args:
    """Mock args for CmdValidate."""
    def __init__(self, flow_file=None, json_output=False, root=None):
        self.flow_file = flow_file
        self.json = json_output
        self.root = root
        self.param_overrides = []
        self.config = None


def test_valid_workflow_passes(tmpdir, capsys):
    """Test valid workflow with produces/consumes passes validation."""
    flow_yaml = """
package:
  name: test_valid
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce"
        - name: Consumer
          needs: [Producer]
          consumes:
            - type: std.FileSet
              filetype: verilog
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0  # No errors
    assert output['valid'] is True
    assert output['error_count'] == 0
    
    # Check that no dataflow warnings were generated
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 0


def test_mismatch_generates_warning(tmpdir, capsys):
    """Test dataflow mismatch generates warning."""
    flow_yaml = """
package:
  name: test_mismatch
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce"
        - name: Consumer
          needs: [Producer]
          consumes:
            - type: std.FileSet
              filetype: vhdl
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    # Should still pass (warnings, not errors)
    assert result == 0
    assert output['valid'] is True
    
    # But should have a DataflowMismatch warning
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 1
    assert 'Producer' in dataflow_warnings[0]['message']
    assert 'Consumer' in dataflow_warnings[0]['message']
    assert 'vhdl' in dataflow_warnings[0]['message']


def test_produces_inheritance_validation(tmpdir, capsys):
    """Test produces inheritance works with validation."""
    flow_yaml = """
package:
  name: test_inherit
  tasks:
    - name: BaseProducer
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "base"
      
    - name: DerivedProducer
      uses: BaseProducer
      produces:
        - type: std.FileSet
          filetype: vhdl
      run: echo "derived"
      
    - root: Main
      body:
        - name: derived
          uses: DerivedProducer
        - name: consumer
          needs: [derived]
          consumes:
            - type: std.FileSet
              filetype: verilog  # Should match inherited produces
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    assert output['valid'] is True
    
    # Should have no dataflow warnings (derived inherits verilog from base)
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 0


def test_chain_of_tasks(tmpdir, capsys):
    """Test chain of tasks with produces/consumes."""
    flow_yaml = """
package:
  name: test_chain
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce"
        - name: Transformer
          needs: [Producer]
          consumes:
            - type: std.FileSet
              filetype: verilog
          produces:
            - type: std.FileSet
              filetype: simLib
          run: echo "transform"
        - name: Consumer
          needs: [Transformer]
          consumes:
            - type: std.FileSet
              filetype: simLib
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    assert result == 0
    assert output['valid'] is True
    
    # All connections should be valid
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 0


def test_multiple_mismatches(tmpdir, capsys):
    """Test multiple dataflow mismatches are all reported."""
    flow_yaml = """
package:
  name: test_multi_mismatch
  tasks:
    - root: Main
      body:
        - name: Producer1
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce1"
        - name: Producer2
          produces:
            - type: std.FileSet
              filetype: vhdl
          run: echo "produce2"
        - name: Consumer1
          needs: [Producer1]
          consumes:
            - type: std.FileSet
              filetype: vhdl  # Mismatch!
          run: echo "consume1"
        - name: Consumer2
          needs: [Producer2]
          consumes:
            - type: std.FileSet
              filetype: verilog  # Mismatch!
          run: echo "consume2"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    # Should report both mismatches
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 2


def test_no_produces_is_compatible(tmpdir, capsys):
    """Test that tasks without produces don't generate warnings."""
    flow_yaml = """
package:
  name: test_no_produces
  tasks:
    - root: Main
      body:
        - name: Producer
          run: echo "produce"  # No produces declared
        - name: Consumer
          needs: [Producer]
          consumes:
            - type: std.FileSet
              filetype: verilog
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    # Should pass - unknown produces assumed compatible
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 0


def test_consumes_all_compatible(tmpdir, capsys):
    """Test that consumes: all accepts any produces."""
    flow_yaml = """
package:
  name: test_consumes_all
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce"
        - name: Consumer
          needs: [Producer]
          # No consumes specified = ConsumesE.All
          run: echo "consume"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    cmd = CmdValidate()
    args = Args(flow_file=str(flow_file), json_output=True)
    
    result = cmd(args)
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    
    # Should pass - ConsumesE.All accepts anything
    dataflow_warnings = [w for w in output['warnings'] if w['type'] == 'DataflowMismatch']
    assert len(dataflow_warnings) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
