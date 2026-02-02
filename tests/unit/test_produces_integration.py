#****************************************************************************
#* test_produces_integration.py
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
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder


def test_produces_in_task_node(tmpdir):
    """Test produces is present in TaskNode after graph building."""
    flow_yaml = """
package:
  name: test_node
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
          run: echo "produce"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=str(tmpdir),
        loader=loader
    )
    
    root_node = builder.mkTaskNode("test_node.Main")
    
    # Root is compound, check its subtask (Producer is the second task after the implicit "in" task)
    assert len(root_node.tasks) == 2
    producer_node = root_node.tasks[1]
    
    assert producer_node.produces is not None
    assert len(producer_node.produces) == 1
    assert producer_node.produces[0]["type"] == "std.FileSet"
    assert producer_node.produces[0]["filetype"] == "verilog"


def test_produces_parameter_evaluation(tmpdir):
    """Test produces with parameter references are evaluated."""
    flow_yaml = """
package:
  name: test_eval
  tasks:
    - root: Main
      body:
        - name: Producer
          with:
            type:
              type: str
              value: verilog
          produces:
            - type: std.FileSet
              filetype: "${{ params.type }}"
          run: echo "produce ${{ type }}"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=str(tmpdir),
        loader=loader
    )
    
    root_node = builder.mkTaskNode("test_eval.Main")
    producer_node = root_node.tasks[1]
    
    # Check that parameter reference was evaluated
    assert producer_node.produces is not None
    assert len(producer_node.produces) == 1
    assert producer_node.produces[0]["filetype"] == "verilog"


def test_produces_multiple_parameters(tmpdir):
    """Test produces with multiple parameter references."""
    flow_yaml = """
package:
  name: test_multi
  tasks:
    - root: Main
      body:
        - name: Producer
          with:
            filetype:
              type: str
              value: verilog
            vendor:
              type: str
              value: synopsys
          produces:
            - type: std.FileSet
              filetype: "${{ params.filetype }}"
              vendor: "${{ params.vendor }}"
          run: echo "produce"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=str(tmpdir),
        loader=loader
    )
    
    root_node = builder.mkTaskNode("test_multi.Main")
    producer_node = root_node.tasks[1]
    
    assert producer_node.produces[0]["filetype"] == "verilog"
    assert producer_node.produces[0]["vendor"] == "synopsys"


def test_produces_inheritance_with_evaluation(tmpdir):
    """Test produces inheritance works with parameter evaluation."""
    flow_yaml = """
package:
  name: test_inherit_eval
  tasks:
    - name: BaseProducer
      produces:
        - type: std.FileSet
          filetype: verilog
      with:
        mode:
          type: str
          value: debug
      run: echo "base"
      
    - name: DerivedProducer
      uses: BaseProducer
      produces:
        - type: std.FileSet
          filetype: "${{ params.mode }}"
      run: echo "derived"
      
    - root: Main
      body:
        - name: prod
          uses: DerivedProducer
          with:
            mode:
              type: str
              value: release
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=str(tmpdir),
        loader=loader
    )
    
    root_node = builder.mkTaskNode("test_inherit_eval.Main")
    prod_node = root_node.tasks[1]
    
    # Should have both inherited produces and new produces (with evaluation)
    assert len(prod_node.produces) == 2
    assert prod_node.produces[0]["filetype"] == "verilog"  # Inherited
    assert prod_node.produces[1]["filetype"] == "release"  # Evaluated from override


def test_produces_no_parameters(tmpdir):
    """Test produces without parameters work correctly."""
    flow_yaml = """
package:
  name: test_no_params
  tasks:
    - root: Main
      body:
        - name: Producer
          produces:
            - type: std.FileSet
              filetype: verilog
              stage: rtl
          run: echo "produce"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=str(tmpdir),
        loader=loader
    )
    
    root_node = builder.mkTaskNode("test_no_params.Main")
    producer_node = root_node.tasks[1]
    
    assert producer_node.produces[0]["type"] == "std.FileSet"
    assert producer_node.produces[0]["filetype"] == "verilog"
    assert producer_node.produces[0]["stage"] == "rtl"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
