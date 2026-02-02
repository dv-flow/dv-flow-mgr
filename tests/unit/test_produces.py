#****************************************************************************
#* test_produces.py
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
from dv_flow.mgr.task_def import TaskDef
from dv_flow.mgr.task import Task
from dv_flow.mgr import PackageLoader


def test_produces_in_taskdef():
    """Test produces field is accepted in TaskDef schema."""
    taskdef = TaskDef(
        name="test",
        produces=[{"type": "std.FileSet", "filetype": "verilog"}]
    )
    assert taskdef.produces is not None
    assert len(taskdef.produces) == 1
    assert taskdef.produces[0]["type"] == "std.FileSet"
    assert taskdef.produces[0]["filetype"] == "verilog"


def test_produces_in_task():
    """Test produces field is stored in Task."""
    task = Task(
        name="test",
        produces=[{"type": "std.FileSet"}]
    )
    assert task.produces is not None
    assert len(task.produces) == 1


def test_multiple_produces_patterns():
    """Test multiple produces patterns are supported."""
    taskdef = TaskDef(
        name="test",
        produces=[
            {"type": "std.FileSet", "filetype": "verilog"},
            {"type": "std.FileSet", "filetype": "vhdl"}
        ]
    )
    assert len(taskdef.produces) == 2
    assert taskdef.produces[0]["filetype"] == "verilog"
    assert taskdef.produces[1]["filetype"] == "vhdl"


def test_empty_produces():
    """Test empty/None produces is handled correctly."""
    task1 = Task(name="test1", produces=None)
    task2 = Task(name="test2", produces=[])
    assert task1.produces is None
    assert task2.produces == []


def test_task_dump_includes_produces():
    """Test Task.dump() includes produces field."""
    task = Task(
        name="test",
        produces=[{"type": "std.FileSet", "filetype": "verilog"}]
    )
    dumped = task.dump()
    assert "produces" in dumped
    assert dumped["produces"] == [{"type": "std.FileSet", "filetype": "verilog"}]


def test_task_dump_excludes_empty_produces():
    """Test Task.dump() excludes empty produces."""
    task = Task(name="test", produces=None)
    dumped = task.dump()
    assert "produces" not in dumped


def test_produces_parsed_from_yaml(tmpdir):
    """Test produces is parsed from YAML correctly."""
    flow_yaml = """
package:
  name: test_produces
  tasks:
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
    
    assert pkg is not None
    assert "test_produces.Producer" in pkg.task_m
    task = pkg.task_m["test_produces.Producer"]
    assert task.produces is not None
    assert len(task.produces) == 1
    assert task.produces[0]["type"] == "std.FileSet"
    assert task.produces[0]["filetype"] == "verilog"


def test_produces_inheritance_extends(tmpdir):
    """Test produces inheritance - derived task extends base produces."""
    flow_yaml = """
package:
  name: test_inheritance
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
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    base_task = pkg.task_m["test_inheritance.BaseProducer"]
    derived_task = pkg.task_m["test_inheritance.DerivedProducer"]
    
    # Base has one produces pattern
    assert len(base_task.produces) == 1
    assert base_task.produces[0]["filetype"] == "verilog"
    
    # Derived extends - should have both verilog (inherited) and vhdl (added)
    assert len(derived_task.produces) == 2
    assert derived_task.produces[0]["filetype"] == "verilog"  # Inherited
    assert derived_task.produces[1]["filetype"] == "vhdl"     # Added


def test_produces_inheritance_base_only(tmpdir):
    """Test produces inheritance - derived task without produces inherits all."""
    flow_yaml = """
package:
  name: test_inheritance_base
  tasks:
    - name: BaseProducer
      produces:
        - type: std.FileSet
          filetype: verilog
      run: echo "base"
      
    - name: DerivedProducer
      uses: BaseProducer
      run: echo "derived"
"""
    flow_file = tmpdir.join("flow.yaml")
    flow_file.write(flow_yaml)
    
    loader = PackageLoader()
    pkg = loader.load(str(flow_file))
    
    base_task = pkg.task_m["test_inheritance_base.BaseProducer"]
    derived_task = pkg.task_m["test_inheritance_base.DerivedProducer"]
    
    # Both should have the same produces
    assert len(base_task.produces) == 1
    assert len(derived_task.produces) == 1
    assert derived_task.produces[0]["filetype"] == "verilog"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
