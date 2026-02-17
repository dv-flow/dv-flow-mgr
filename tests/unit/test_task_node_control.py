#****************************************************************************
#* test_task_node_control.py
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
#*
#****************************************************************************
import pytest
from dv_flow.mgr.task_node_control import TaskNodeControl
from dv_flow.mgr.task_def import ControlDef, ControlStateDef
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt


def make_test_ctxt():
    """Helper to create a test TaskNodeCtxt"""
    return TaskNodeCtxt(
        root_pkgdir='/tmp/pkg',
        root_rundir='/tmp/run',
        env={}
    )


class TestConditionEvaluation:
    """Test condition evaluation in control nodes"""
    
    def test_simple_equality_condition(self):
        """Test evaluating a simple equality condition"""
        control_def = ControlDef(type='if', cond='${{ state.value == 5 }}')
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=control_def
        )
        
        node.state = {'value': 5}
        assert node._eval_condition('${{ state.value == 5 }}') is True
        
        node.state = {'value': 10}
        assert node._eval_condition('${{ state.value == 5 }}') is False
    
    def test_comparison_condition(self):
        """Test evaluating comparison conditions"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='while', cond='', max_iter=5)
        )
        
        node.state = {'score': 95}
        assert node._eval_condition('${{ state.score >= 90 }}') is True
        assert node._eval_condition('${{ state.score > 100 }}') is False
    
    def test_logical_condition(self):
        """Test evaluating logical conditions"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='if', cond='')
        )
        
        node.state = {'passed': True, 'score': 85}
        assert node._eval_condition('${{ state.passed && state.score > 80 }}') is True
        assert node._eval_condition('${{ state.passed && state.score > 90 }}') is False
        assert node._eval_condition('${{ !state.passed || state.score > 90 }}') is False
    
    def test_condition_without_wrapper(self):
        """Test conditions work with or without ${{ }} wrapper"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='if', cond='')
        )
        
        node.state = {'value': True}
        assert node._eval_condition('state.value') is True
        assert node._eval_condition('${{ state.value }}') is True


class TestStateManagement:
    """Test state initialization and management"""
    
    def test_state_initialization_from_control_def(self):
        """Test that state is initialized from control_def.state.init"""
        control_def = ControlDef(
            type='do-while',
            until='${{ state.done }}',
            max_iter=5,
            state=ControlStateDef(init={'iteration': 0, 'done': False})
        )
        
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=control_def
        )
        
        assert node.state['iteration'] == 0
        assert node.state['done'] is False
    
    def test_inject_iteration_vars(self):
        """Test automatic injection of _iter and _max_iter"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='repeat', count=5)
        )
        
        state = {'value': 10}
        node._inject_iteration_vars(state, iteration=2, max_iter=5)
        
        assert state['_iter'] == 2
        assert state['_max_iter'] == 5
        assert state['value'] == 10  # Original values preserved
    
    def test_extract_output_state(self):
        """Test extracting state from body output"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='if', cond='')
        )
        
        # Mock output items
        class MockOutput:
            def __init__(self, data):
                self.data = data
        
        body_output = [
            MockOutput({'result': 'success', 'score': 95}),
            MockOutput({'iteration': 1})
        ]
        
        state = node._extract_output_state(body_output)
        assert state['result'] == 'success'
        assert state['score'] == 95
        assert state['iteration'] == 1


class TestFeedbackTransform:
    """Test feedback expression transformation"""
    
    def test_no_feedback_passthrough(self):
        """Test that without feedback expression, output passes through"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='repeat', count=3)
        )
        
        output = {'value': 10, 'status': 'ok'}
        result = node._apply_feedback(output)
        assert result == output
    
    def test_feedback_simple_passthrough(self):
        """Test feedback with simple state transformation"""
        control_def = ControlDef(
            type='while',
            cond='${{ state.attempt < 3 }}',
            max_iter=3,
            state=ControlStateDef(
                # For now, feedback without complex nested expressions
                init={'attempt': 0}
            )
        )
        
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=control_def
        )
        
        # Test that output passes through when no feedback expression
        output = {'attempt': 1, 'value': 'test'}
        result = node._apply_feedback(output)
        assert isinstance(result, dict)
        assert result == output


class TestBreakSignal:
    """Test _break signal detection"""
    
    def test_break_signal_present(self):
        """Test detecting _break signal"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='repeat', count=10)
        )
        
        state_with_break = {'_break': True, 'value': 42}
        assert node._check_break_signal(state_with_break) is True
    
    def test_break_signal_absent(self):
        """Test no break when signal absent"""
        node = TaskNodeControl(
            name='test',
            srcdir='/tmp',
            params={},
            ctxt=make_test_ctxt(),
            control_def=ControlDef(type='repeat', count=10)
        )
        
        state_no_break = {'value': 42}
        assert node._check_break_signal(state_no_break) is False
        
        state_false_break = {'_break': False, 'value': 42}
        assert node._check_break_signal(state_false_break) is False
