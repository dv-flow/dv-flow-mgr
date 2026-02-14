#****************************************************************************
#* test_deferred_expr_integration.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
"""
Integration tests for deferred expression evaluation with real task execution.
Tests that expressions referencing 'inputs' and 'memento' are correctly deferred
during graph construction and evaluated at task runtime.
"""
import os
import json
import pytest
import tempfile
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.deferred_expr import DeferredExpr


class TestDeferredExpressionIntegration:
    """Integration tests for deferred expressions with inputs"""
    
    @pytest.mark.asyncio
    async def test_simple_input_reference(self, tmp_path):
        """Test that ${{ inputs }} is deferred and evaluated at runtime"""
        
        # Create a test package with producer and consumer tasks
        flow_yaml = tmp_path / "flow.dv"
        flow_yaml.write_text("""
package:
  name: test_deferred
  
  tasks:
    # Producer task that outputs data items
    - name: producer
      scope: root
      produces: [std.FileSet]
      run: echo '{"type":"std.FileSet","name":"file1"}'
      shell: bash
    
    # Consumer task that uses deferred expression to access inputs
    - name: consumer
      scope: root
      consumes: [std.FileSet]
      with:
        input_data:
          type: str
          # This expression references 'inputs' and should be deferred
          value: "${{ inputs }}"
      run: 'echo "Received inputs: ${input_data}"'
      shell: bash
      needs: [producer]
""")
        
        # Set up rundir
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir, exist_ok=True)
        
        # Load package using standard utility
        loader, pkg = loadProjPkgDef(str(tmp_path))
        
        # Build task graph
        builder = TaskGraphBuilder(
            root_pkg=pkg,
            rundir=rundir,
            loader=loader
        )
        
        # Build the consumer task node (which depends on producer)
        consumer_node = builder.mkTaskNode("test_deferred.consumer")
        
        assert consumer_node is not None, "Consumer node not found"
        
        # Check that input_data parameter contains a DeferredExpr
        input_data_value = consumer_node.params.input_data
        assert isinstance(input_data_value, DeferredExpr), \
            f"Expected DeferredExpr, got {type(input_data_value)}"
        assert "inputs" in input_data_value.expr_str, \
            f"Expression should reference 'inputs': {input_data_value.expr_str}"
        
        # Execute the task graph
        runner = TaskSetRunner(rundir=rundir)
        await runner.run_node_tree(consumer_node)
        
        # Check execution succeeded
        assert runner.status == 0, f"Task execution failed with status {runner.status}"
    
    @pytest.mark.asyncio
    async def test_input_length_expression(self, tmp_path):
        """Test expression that computes length of inputs"""
        
        flow_yaml = tmp_path / "flow.dv"
        flow_yaml.write_text("""
package:
  name: test_length
  
  tasks:
    - name: producer
      scope: root
      produces: [std.FileSet]
      run: echo '{"type":"std.FileSet","name":"test"}'
    
    - name: consumer
      scope: root
      consumes: [std.FileSet]
      with:
        count:
          type: int
          # This won't work yet (no native length builtin)
          # But the deferred expression should still be created
          value: "${{ inputs }}"
      run: 'echo "Count: ${count}"'
      needs: [producer]
""")
        
        # Set up rundir
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir, exist_ok=True)
        
        # Load package using standard utility
        loader, pkg = loadProjPkgDef(str(tmp_path))
        
        # Build task graph
        builder = TaskGraphBuilder(
            root_pkg=pkg,
            rundir=rundir,
            loader=loader
        )
        
        # Build the consumer task node
        consumer_node = builder.mkTaskNode("test_length.consumer")
        
        # Verify deferred expression
        assert consumer_node is not None
        assert isinstance(consumer_node.params.count, DeferredExpr)
        
        # Execute
        runner = TaskSetRunner(rundir=rundir)
        await runner.run_node_tree(consumer_node)
        assert runner.status == 0
    
    @pytest.mark.asyncio
    async def test_mixed_static_and_deferred(self, tmp_path):
        """Test task with both static and deferred parameters"""
        
        flow_yaml = tmp_path / "flow.dv"
        flow_yaml.write_text("""
package:
  name: test_mixed
  
  with:
    static_value:
      type: str
      value: "I am static"
  
  tasks:
    - name: producer
      scope: root
      produces: [std.FileSet]
      run: echo '{"type":"std.FileSet","name":"data"}'
    
    - name: consumer
      scope: root
      consumes: [std.FileSet]
      with:
        static_param:
          type: str
          # This references package param - should be evaluated at graph build
          value: "${{ static_value }}"
        dynamic_param:
          type: str
          # This references inputs - should be deferred
          value: "${{ inputs }}"
        mixed_param:
          type: str
          # This references both - should be deferred
          value: "${{ static_value }} and ${{ inputs }}"
      run: |
        echo "static_param: ${static_param}"
        echo "dynamic_param: ${dynamic_param}"
        echo "mixed_param: ${mixed_param}"
      needs: [producer]
""")
        
        # Set up rundir
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir, exist_ok=True)
        
        # Load package using standard utility
        loader, pkg = loadProjPkgDef(str(tmp_path))
        
        # Build task graph
        builder = TaskGraphBuilder(
            root_pkg=pkg,
            rundir=rundir,
            loader=loader
        )
        
        # Build the consumer task node
        consumer_node = builder.mkTaskNode("test_mixed.consumer")
        
        # Verify parameter evaluation
        assert consumer_node is not None
        
        # static_param should be evaluated to the string
        assert consumer_node.params.static_param == "I am static", \
            f"static_param should be evaluated at build time"
        
        # dynamic_param should be deferred
        assert isinstance(consumer_node.params.dynamic_param, DeferredExpr), \
            f"dynamic_param should be deferred"
        
        # mixed_param should be deferred (contains inputs reference)
        assert isinstance(consumer_node.params.mixed_param, DeferredExpr), \
            f"mixed_param should be deferred (contains inputs)"
        
        # Execute
        runner = TaskSetRunner(rundir=rundir)
        await runner.run_node_tree(consumer_node)
        assert runner.status == 0
    
    @pytest.mark.asyncio
    async def test_memento_deferred(self, tmp_path):
        """Test that expressions referencing memento are deferred"""
        
        flow_yaml = tmp_path / "flow.dv"
        flow_yaml.write_text("""
package:
  name: test_memento
  
  tasks:
    - name: with_memento
      scope: root
      with:
        prev_run:
          type: str
          # This references memento - should be deferred
          value: "${{ memento }}"
      run: 'echo "Previous run data: ${prev_run}"'
""")
        
        # Set up rundir
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir, exist_ok=True)
        
        # Load package using standard utility
        loader, pkg = loadProjPkgDef(str(tmp_path))
        
        # Build task graph
        builder = TaskGraphBuilder(
            root_pkg=pkg,
            rundir=rundir,
            loader=loader
        )
        
        # Build the task node
        memento_node = builder.mkTaskNode("test_memento.with_memento")
        
        # Verify deferred
        assert memento_node is not None
        assert isinstance(memento_node.params.prev_run, DeferredExpr), \
            "memento reference should be deferred"
        
        # Execute
        runner = TaskSetRunner(rundir=rundir)
        await runner.run_node_tree(memento_node)
        assert runner.status == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
