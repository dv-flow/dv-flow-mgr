#****************************************************************************
#* test_llm_server_integration.py
#*
#* Integration tests for LLM call interface with actual task execution
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
"""
Integration tests for the LLM Call Interface.

These tests verify the complete workflow:
1. TaskSetRunner starts with command server
2. Environment variable is set for child processes
3. Client can connect and execute commands
4. Results are properly returned
"""

import asyncio
import json
import os
import pytest
import sys
import subprocess
from pathlib import Path


class TestServerIntegrationWithRealProject:
    """Integration tests with actual DFM projects"""
    
    @pytest.mark.asyncio
    async def test_server_runs_with_real_task(self, tmp_path):
        """Test server running actual tasks through dynamic scheduling"""
        from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
        from dv_flow.mgr.dfm_server import DfmClient
        
        # Create a simple project
        flow_content = """
package:
  name: test_project
  
  tasks:
    - name: hello
      scope: root
      uses: std.Message
      with:
        msg: "Hello from task!"
    
    - name: data
      scope: root
      uses: std.FileSet
      with:
        type: text
        include: "*.txt"
"""
        flow_file = tmp_path / 'flow.dv'
        flow_file.write_text(flow_content)
        (tmp_path / 'test.txt').write_text("Test file content")
        
        rundir = tmp_path / 'rundir'
        rundir.mkdir()
        
        # Load the package
        loader = PackageLoader()
        pkg = loader.load(str(flow_file))
        
        # Build runner with server
        builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(rundir), loader=loader)
        runner = TaskSetRunner(str(rundir), builder=builder, enable_server=True)
        
        # Run the task
        task = builder.mkTaskNode("test_project.hello")
        result = await runner.run(task)
        
        # Verify task completed successfully
        assert result is not None
        
        # Verify env was set during run
        assert "DFM_SERVER_SOCKET" in runner.env
        assert "DFM_SESSION_RUNDIR" in runner.env
    
    @pytest.mark.asyncio
    async def test_environment_variable_is_set(self, tmp_path):
        """Test that DFM_SERVER_SOCKET is set in runner environment"""
        from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
        
        # Create a simple project
        flow_content = """
package:
  name: env_test
  
  tasks:
    - name: check
      scope: root
      uses: std.Message
      with:
        msg: "Check env"
"""
        flow_file = tmp_path / 'flow.dv'
        flow_file.write_text(flow_content)
        
        rundir = tmp_path / 'rundir'
        rundir.mkdir()
        
        # Load the package
        loader = PackageLoader()
        pkg = loader.load(str(flow_file))
        
        # Build runner
        builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(rundir), loader=loader)
        runner = TaskSetRunner(str(rundir), builder=builder, enable_server=True)
        
        # Initially no socket path
        assert runner.server_socket_path is None
        
        # Create and run a task
        task = builder.mkTaskNode("env_test.check")
        await runner.run(task)
        
        # After run, server should have been started and env set
        # Note: server stops after run completes
        assert "DFM_SERVER_SOCKET" in runner.env
        assert "DFM_SESSION_RUNDIR" in runner.env
        assert runner.env["DFM_SESSION_RUNDIR"] == str(rundir)


class TestClientCliIntegration:
    """Tests for the CLI client mode"""
    
    def test_client_help_in_server_mode(self, tmp_path):
        """Test that client shows usage when no command given"""
        socket_path = str(tmp_path / "test.sock")
        
        result = subprocess.run(
            [sys.executable, "-m", "dv_flow.mgr"],
            env={**os.environ, "DFM_SERVER_SOCKET": socket_path},
            capture_output=True,
            text=True
        )
        
        # Should show usage message
        assert "Usage" in result.stderr or result.returncode != 0
    
    def test_client_run_without_tasks(self, tmp_path):
        """Test that run command requires tasks"""
        socket_path = str(tmp_path / "test.sock")
        
        # Even with non-existent socket, should fail fast on missing tasks
        result = subprocess.run(
            [sys.executable, "-m", "dv_flow.mgr", "run"],
            env={**os.environ, "DFM_SERVER_SOCKET": socket_path},
            capture_output=True,
            text=True
        )
        
        # Should report error (either about socket or missing tasks)
        assert result.returncode != 0 or "error" in result.stderr.lower()


class TestServerProtocol:
    """Tests for the JSON-RPC protocol"""
    
    @pytest.mark.asyncio
    async def test_malformed_json_handled(self, tmp_path):
        """Test that server handles malformed JSON gracefully"""
        from dv_flow.mgr.dfm_server import DfmCommandServer
        
        class MockRunner:
            rundir = str(tmp_path)
        
        class MockBuilder:
            class MockPkg:
                name = "test_pkg"
                task_m = {}
                type_m = {}
                pkg_m = {}
                basedir = str(tmp_path)
            root_pkg = MockPkg()
        
        server = DfmCommandServer(
            runner=MockRunner(),
            builder=MockBuilder()
        )
        
        await server.start()
        
        try:
            # Connect directly and send malformed JSON
            reader, writer = await asyncio.open_unix_connection(server.socket_path)
            
            # Send invalid JSON
            writer.write(b'{"invalid json\n')
            await writer.drain()
            
            # Read response
            response_line = await reader.readline()
            response = json.loads(response_line)
            
            # Should return JSON-RPC error
            assert "error" in response
            assert response["error"]["code"] == -32700  # Parse error
            
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, tmp_path):
        """Test that server handles concurrent requests"""
        from dv_flow.mgr.dfm_server import DfmCommandServer, DfmClient
        
        class MockRunner:
            rundir = str(tmp_path)
        
        class MockBuilder:
            class MockPkg:
                name = "test_pkg"
                task_m = {}
                type_m = {}
                pkg_m = {}
                basedir = str(tmp_path)
            root_pkg = MockPkg()
        
        server = DfmCommandServer(
            runner=MockRunner(),
            builder=MockBuilder()
        )
        
        await server.start()
        
        try:
            # Create multiple clients
            clients = [DfmClient(server.socket_path) for _ in range(3)]
            
            # Send concurrent ping requests
            async def ping_client(client):
                result = await client.ping()
                return result["status"]
            
            results = await asyncio.gather(*[ping_client(c) for c in clients])
            
            # All should succeed
            assert all(r == "ok" for r in results)
            
            # Cleanup
            for client in clients:
                await client.disconnect()
        finally:
            await server.stop()
