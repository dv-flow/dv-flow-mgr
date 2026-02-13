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
import pytest
import tempfile
from dv_flow.mgr.task_runner import TaskSetRunner


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
      produces: [std.FileSet]
      run: |
        import json
        # Output some test data
        outputs = [
            {"type": "std.FileSet", "name": "file1"},
            {"type": "std.FileSet", "name": "file2"},
            {"type": "std.FileSet", "name": "file3"}
        ]
        print(json.dumps(outputs))
      shell: python3
    
    # Consumer task that uses deferred expression to access inputs
    - name: consumer
      consumes: [std.FileSet]
      with:
        input_data:
          type: str
          # This expression references 'inputs' and should be deferred
          value: "${{ inputs }}"
      run: |
        import json
        # Verify we received the inputs
        inputs_str = "${input_data}"
        print(f"Received inputs: {inputs_str}")
        
        # Parse and validate
        try:
            inputs_list = json.loads(inputs_str)
            assert isinstance(inputs_list, list), "inputs should be a list"
            assert len(inputs_list) == 3, f"Expected 3 inputs, got {len(inputs_list)}"
            print(f"SUCCESS: Received {len(inputs_list)} inputs")
        except Exception as e:
            print(f"ERROR: {e}")
            exit(1)
      shell: python3
      needs: [producer]
""")
        
        # Create runner and execute
        runner = TaskSetRunner(rundir=str(tmp_path / "rundir"))
        os.makedirs(runner.rundir, exist_ok=True)
        
        # Load package and build graph
        from dv_flow.mgr.package_loader_p import PackageLoaderP
        loader = PackageLoaderP()
        pkg = loader.load_package(str(flow_yaml))
        
        # Build task graph
        from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
        builder = TaskGraphBuilder()
        root_node = builder.build_graph(pkg, "consumer")
        
        # Verify deferred expression was created
        consumer_node = None
        for node in builder._task_m.values():
            if node.name == "test_deferred.consumer":
                consumer_node = node
                break
        
        assert consumer_node is not None, "Consumer node not found"
        
        # Check that input_data parameter contains a DeferredExpr
        from dv_flow.mgr.deferred_expr import DeferredExpr
        input_data_value = consumer_node.params.input_data
        assert isinstance(input_data_value, DeferredExpr), \
            f"Expected DeferredExpr, got {type(input_data_value)}"
        assert "inputs" in input_data_value.expr_str, \
            f"Expression should reference 'inputs': {input_data_value.expr_str}"
        
        # Execute the task graph
        await runner.run_node_tree(root_node)
        
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
      produces: [std.FileSet]
      run: |
        # Output 5 items
        for i in range(5):
            print(f"Item {i}")
      shell: python3
    
    - name: consumer
      consumes: [std.FileSet]
      with:
        count:
          type: int
          # This won't work yet (no native length builtin)
          # But the deferred expression should still be created
          value: "${{ inputs }}"
      run: |
        import json
        inputs_str = "${count}"
        inputs = json.loads(inputs_str) if isinstance(inputs_str, str) and inputs_str.startswith('[') else inputs_str
        
        # Count the inputs
        if isinstance(inputs, list):
            count = len(inputs)
            print(f"Received {count} inputs")
            assert count > 0, "Should have received inputs"
        else:
            print(f"inputs type: {type(inputs)}")
            print(f"inputs value: {inputs}")
      shell: python3
      needs: [producer]
""")
        
        runner = TaskSetRunner(rundir=str(tmp_path / "rundir"))
        os.makedirs(runner.rundir, exist_ok=True)
        
        from dv_flow.mgr.package_loader_p import PackageLoaderP
        loader = PackageLoaderP()
        pkg = loader.load_package(str(flow_yaml))
        
        from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
        builder = TaskGraphBuilder()
        root_node = builder.build_graph(pkg, "consumer")
        
        # Verify deferred expression
        from dv_flow.mgr.deferred_expr import DeferredExpr
        consumer_node = builder._task_m.get("test_length.consumer")
        assert consumer_node is not None
        assert isinstance(consumer_node.params.count, DeferredExpr)
        
        # Execute
        await runner.run_node_tree(root_node)
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
      produces: [std.FileSet]
      run: |
        print("Producing data")
      shell: python3
    
    - name: consumer
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
        static = "${static_param}"
        dynamic = "${dynamic_param}"
        mixed = "${mixed_param}"
        
        print(f"static_param: {static}")
        print(f"dynamic_param: {dynamic}")
        print(f"mixed_param: {mixed}")
        
        # Static should be evaluated
        assert static == "I am static", f"Expected 'I am static', got '{static}'"
        
        # Dynamic should have inputs data
        assert "inputs" in dynamic.lower() or "[" in dynamic, \
            f"dynamic_param should contain inputs: {dynamic}"
        
        print("SUCCESS: Mixed static/dynamic parameters work")
      shell: python3
      needs: [producer]
""")
        
        runner = TaskSetRunner(rundir=str(tmp_path / "rundir"))
        os.makedirs(runner.rundir, exist_ok=True)
        
        from dv_flow.mgr.package_loader_p import PackageLoaderP
        loader = PackageLoaderP()
        pkg = loader.load_package(str(flow_yaml))
        
        from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
        builder = TaskGraphBuilder()
        root_node = builder.build_graph(pkg, "consumer")
        
        # Verify parameter evaluation
        from dv_flow.mgr.deferred_expr import DeferredExpr
        consumer_node = builder._task_m.get("test_mixed.consumer")
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
        await runner.run_node_tree(root_node)
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
      with:
        prev_run:
          type: str
          # This references memento - should be deferred
          value: "${{ memento }}"
      run: |
        prev = "${prev_run}"
        print(f"Previous run data: {prev}")
        print("Memento test complete")
      shell: python3
""")
        
        runner = TaskSetRunner(rundir=str(tmp_path / "rundir"))
        os.makedirs(runner.rundir, exist_ok=True)
        
        from dv_flow.mgr.package_loader_p import PackageLoaderP
        loader = PackageLoaderP()
        pkg = loader.load_package(str(flow_yaml))
        
        from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
        builder = TaskGraphBuilder()
        root_node = builder.build_graph(pkg, "with_memento")
        
        # Verify deferred
        from dv_flow.mgr.deferred_expr import DeferredExpr
        memento_node = builder._task_m.get("test_memento.with_memento")
        assert memento_node is not None
        assert isinstance(memento_node.params.prev_run, DeferredExpr), \
            "memento reference should be deferred"
        
        # Execute
        await runner.run_node_tree(root_node)
        assert runner.status == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
