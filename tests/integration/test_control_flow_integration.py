#****************************************************************************
#* test_control_flow_integration.py
#*
#* Test integration of control flow constructs with task graph builder
#*
#****************************************************************************
import pytest
import os
import tempfile
import yaml
from pathlib import Path


@pytest.fixture
def test_flow_dir():
    """Create a temporary directory with a test flow"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestIfControlFlow:
    """Test if/else control flow integration"""
    
    def test_if_construct_schema_validation(self, test_flow_dir):
        """Test that if control construct validates correctly"""
        flow_yaml = """
package:
  name: test_if
  
  tasks:
    - name: check_value
      run: echo '{"value":5}'
      
    - root: conditional_task
      needs: [check_value]
      control:
        type: if
        cond: '${{ in.value == 5 }}'
      body:
        - name: when_five
          run: echo "Value is 5"
"""
        flow_file = test_flow_dir / "flow.yaml"
        flow_file.write_text(flow_yaml)
        
        # Test that the YAML loads and validates
        from dv_flow.mgr.package_def import PackageDef
        
        with open(flow_file) as f:
            data = yaml.safe_load(f)
        
        # This should not raise an exception
        pkg_def = PackageDef(**data['package'])
        
        # Verify the control field is present
        assert pkg_def.tasks[1].control is not None
        assert pkg_def.tasks[1].control.type == 'if'
        assert pkg_def.tasks[1].control.cond is not None


class TestDoWhileControlFlow:
    """Test do-while control flow integration"""
    
    def test_do_while_construct_schema_validation(self, test_flow_dir):
        """Test that do-while control construct validates correctly"""
        flow_yaml = """
package:
  name: test_do_while
  
  tasks:
    - root: retry_loop
      control:
        type: do-while
        until: '${{ state.success == true }}'
        max_iter: 3
        state:
          init:
            success: false
            attempt: 0
      body:
        - name: attempt_task
          run: |
            echo '{"success":true,"attempt":1}'
"""
        flow_file = test_flow_dir / "flow.yaml"
        flow_file.write_text(flow_yaml)
        
        from dv_flow.mgr.package_def import PackageDef
        
        with open(flow_file) as f:
            data = yaml.safe_load(f)
        
        pkg_def = PackageDef(**data['package'])
        
        # Verify the control field is present and properly structured
        assert pkg_def.tasks[0].control is not None
        assert pkg_def.tasks[0].control.type == 'do-while'
        assert pkg_def.tasks[0].control.until is not None
        assert pkg_def.tasks[0].control.max_iter == 3
        assert pkg_def.tasks[0].control.state is not None
        assert pkg_def.tasks[0].control.state.init['success'] is False


class TestWhileControlFlow:
    """Test while control flow integration"""
    
    def test_while_construct_schema_validation(self, test_flow_dir):
        """Test that while control construct validates correctly"""
        flow_yaml = """
package:
  name: test_while
  
  tasks:
    - root: wait_loop
      control:
        type: while
        cond: '${{ state.status != "ready" }}'
        max_iter: 10
        state:
          init:
            status: pending
            attempt: 0
      body:
        - name: check_status
          run: echo '{"status":"ready"}'
"""
        flow_file = test_flow_dir / "flow.yaml"
        flow_file.write_text(flow_yaml)
        
        from dv_flow.mgr.package_def import PackageDef
        
        with open(flow_file) as f:
            data = yaml.safe_load(f)
        
        pkg_def = PackageDef(**data['package'])
        
        assert pkg_def.tasks[0].control is not None
        assert pkg_def.tasks[0].control.type == 'while'
        assert pkg_def.tasks[0].control.cond is not None
        assert pkg_def.tasks[0].control.max_iter == 10


class TestRepeatControlFlow:
    """Test repeat control flow integration"""
    
    def test_repeat_construct_schema_validation(self, test_flow_dir):
        """Test that repeat control construct validates correctly"""
        flow_yaml = """
package:
  name: test_repeat
  
  tasks:
    - root: refine_loop
      control:
        type: repeat
        count: 5
        until: '${{ state.quality >= 0.9 }}'
        state:
          init:
            quality: 0.5
      body:
        - name: improve
          run: echo '{"quality":0.95}'
"""
        flow_file = test_flow_dir / "flow.yaml"
        flow_file.write_text(flow_yaml)
        
        from dv_flow.mgr.package_def import PackageDef
        
        with open(flow_file) as f:
            data = yaml.safe_load(f)
        
        pkg_def = PackageDef(**data['package'])
        
        assert pkg_def.tasks[0].control is not None
        assert pkg_def.tasks[0].control.type == 'repeat'
        assert pkg_def.tasks[0].control.count == 5
        assert pkg_def.tasks[0].control.until is not None


class TestMatchControlFlow:
    """Test match control flow integration"""
    
    def test_match_construct_schema_validation(self, test_flow_dir):
        """Test that match control construct validates correctly"""
        flow_yaml = """
package:
  name: test_match
  
  tasks:
    - root: route_task
      control:
        type: match
        cases:
          - when: '${{ in.category == "bug" }}'
            body:
              - name: fix_bug
                run: echo "Fixing bug"
          - when: '${{ in.category == "feature" }}'
            body:
              - name: add_feature
                run: echo "Adding feature"
          - default: true
            body:
              - name: log_unknown
                run: echo "Unknown category"
"""
        flow_file = test_flow_dir / "flow.yaml"
        flow_file.write_text(flow_yaml)
        
        from dv_flow.mgr.package_def import PackageDef
        
        with open(flow_file) as f:
            data = yaml.safe_load(f)
        
        pkg_def = PackageDef(**data['package'])
        
        assert pkg_def.tasks[0].control is not None
        assert pkg_def.tasks[0].control.type == 'match'
        assert len(pkg_def.tasks[0].control.cases) == 3
        assert pkg_def.tasks[0].control.cases[0].when is not None
        assert pkg_def.tasks[0].control.cases[2].default is True


class TestControlFlowValidation:
    """Test control flow validation rules"""
    
    def test_control_and_strategy_mutual_exclusion(self):
        """Test that control and strategy cannot both be specified"""
        from dv_flow.mgr.task_def import TaskDef, ControlDef, StrategyDef
        from pydantic import ValidationError
        
        # This should raise a validation error
        with pytest.raises(ValidationError, match="mutually exclusive"):
            task = TaskDef(
                name="bad_task",
                control=ControlDef(type='if', cond='true'),
                strategy=StrategyDef(chain=True)
            )
    
    def test_if_requires_cond(self):
        """Test that if control type requires cond field"""
        from dv_flow.mgr.task_def import ControlDef
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError, match="'if' control type requires 'cond'"):
            control = ControlDef(type='if')
    
    def test_do_while_requires_until_and_max_iter(self):
        """Test that do-while requires until and max_iter"""
        from dv_flow.mgr.task_def import ControlDef
        from pydantic import ValidationError
        
        # Missing until
        with pytest.raises(ValidationError, match="'do-while' control type requires 'until'"):
            control = ControlDef(type='do-while', max_iter=5)
        
        # Missing max_iter
        with pytest.raises(ValidationError, match="'do-while' control type requires 'max_iter'"):
            control = ControlDef(type='do-while', until='true')
    
    def test_while_requires_cond_and_max_iter(self):
        """Test that while requires cond and max_iter"""
        from dv_flow.mgr.task_def import ControlDef
        from pydantic import ValidationError
        
        # Missing cond
        with pytest.raises(ValidationError, match="'while' control type requires 'cond'"):
            control = ControlDef(type='while', max_iter=5)
        
        # Missing max_iter
        with pytest.raises(ValidationError, match="'while' control type requires 'max_iter'"):
            control = ControlDef(type='while', cond='true')
    
    def test_repeat_requires_count(self):
        """Test that repeat requires count"""
        from dv_flow.mgr.task_def import ControlDef
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError, match="'repeat' control type requires 'count'"):
            control = ControlDef(type='repeat')
    
    def test_match_requires_cases(self):
        """Test that match control type requires cases"""
        from pydantic import ValidationError
        from dv_flow.mgr.task_def import ControlDef
        
        with pytest.raises(ValidationError, match="'match' control type requires at least one 'cases'"):
            control = ControlDef(type='match')
