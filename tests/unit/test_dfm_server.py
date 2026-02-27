#****************************************************************************
#* test_dfm_server.py
#*
#* Tests for the DFM command server (LLM call interface)
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
Tests for the DFM Command Server.

These tests verify that the JSON-RPC server correctly handles commands
from LLM assistant processes and returns properly formatted responses.
"""

import asyncio
import json
import os
import pytest
import tempfile
from pathlib import Path


class TestDfmServerBasic:
    """Basic tests for server startup and communication"""
    
    def test_server_starts_and_stops(self, tmp_path):
        """Test that server can start and stop cleanly"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            assert os.path.exists(server.socket_path)
            await server.stop()
            assert not os.path.exists(server.socket_path)

        asyncio.run(_run())
    
    def test_ping_command(self, tmp_path):
        """Test ping command for health checks"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.ping()
                assert result["status"] == "ok"
                assert result["server"] == "dfm"
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())
    
    def test_invalid_method_returns_error(self, tmp_path):
        """Test that invalid method names return proper error"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                with pytest.raises(Exception) as exc_info:
                    await client.call("nonexistent_method")
                assert "Unknown method" in str(exc_info.value)
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())


class TestShowCommands:
    """Tests for show.* commands"""
    
    def test_show_tasks_empty(self, tmp_path):
        """Test show.tasks with no tasks defined"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.show_tasks()
                assert "results" in result
                assert "count" in result
                assert result["count"] == 0
                assert result["results"] == []
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())
    
    def test_show_tasks_with_tasks(self, tmp_path):
        """Test show.tasks with tasks defined"""
        from dv_flow.mgr.dfm_server import DfmCommandServer, DfmClient

        class MockTask:
            def __init__(self, name, desc="", is_root=False, uses=None):
                self.name = name
                self.desc = desc
                self.is_root = is_root
                self.uses = uses

        class MockRunner:
            rundir = str(tmp_path)

        class MockBuilder:
            class MockPkg:
                name = "test_pkg"
                task_m = {
                    "test_pkg.build": MockTask("test_pkg.build", "Build task", is_root=True),
                    "test_pkg.test": MockTask("test_pkg.test", "Test task", is_root=True, uses="std.Message"),
                    "test_pkg.internal": MockTask("test_pkg.internal", "Internal task"),
                }
                type_m = {}
                pkg_m = {}
                basedir = str(tmp_path)
            root_pkg = MockPkg()

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.show_tasks()
                assert result["count"] == 3
                task_names = [t["name"] for t in result["results"]]
                assert "test_pkg.build" in task_names
                assert "test_pkg.test" in task_names
                assert "test_pkg.internal" in task_names

                result = await client.show_tasks(scope="root")
                assert result["count"] == 2

                result = await client.show_tasks(search="build")
                assert result["count"] == 1
                assert result["results"][0]["name"] == "test_pkg.build"
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())
    
    def test_show_task_details(self, tmp_path):
        """Test show.task for specific task details"""
        from dv_flow.mgr.dfm_server import DfmCommandServer, DfmClient

        class MockTask:
            def __init__(self, name, desc="", is_root=False, uses=None, doc=None, params=None, needs=None):
                self.name = name
                self.desc = desc
                self.is_root = is_root
                self.uses = uses
                self.doc = doc
                self.params = params or []
                self.needs = needs or []

        class MockRunner:
            rundir = str(tmp_path)

        class MockBuilder:
            class MockPkg:
                name = "test_pkg"
                task_m = {
                    "test_pkg.build": MockTask(
                        "test_pkg.build",
                        desc="Build the project",
                        is_root=True,
                        uses="std.Message",
                        doc="Builds all RTL and runs compilation"
                    ),
                }
                type_m = {}
                pkg_m = {}
                basedir = str(tmp_path)
            root_pkg = MockPkg()

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.show_task("test_pkg.build")
                assert result["name"] == "test_pkg.build"
                assert result["desc"] == "Build the project"
                assert result["scope"] == "root"
                assert result["uses"] == "std.Message"
                assert result["doc"] == "Builds all RTL and runs compilation"
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())
    
    def test_show_task_not_found(self, tmp_path):
        """Test show.task returns error for unknown task"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                with pytest.raises(Exception) as exc_info:
                    await client.show_task("nonexistent")
                assert "not found" in str(exc_info.value).lower()
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())


class TestContextCommand:
    """Tests for context command"""
    
    def test_context_returns_project_info(self, tmp_path):
        """Test that context returns complete project information"""
        from dv_flow.mgr.dfm_server import DfmCommandServer, DfmClient

        class MockTask:
            def __init__(self, name, desc="", is_root=False, uses=None):
                self.name = name
                self.desc = desc
                self.is_root = is_root
                self.uses = uses

        class MockType:
            def __init__(self, name, desc=""):
                self.name = name
                self.desc = desc

        class MockRunner:
            rundir = str(tmp_path / "rundir")

        class MockBuilder:
            class MockPkg:
                name = "my_project"
                task_m = {
                    "my_project.build": MockTask("my_project.build", "Build", is_root=True),
                }
                type_m = {
                    "my_project.MyType": MockType("my_project.MyType", "Custom type"),
                }
                pkg_m = {}
                basedir = str(tmp_path)
            root_pkg = MockPkg()

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.context()
                assert "project" in result
                assert result["project"]["name"] == "my_project"
                assert "tasks" in result
                assert len(result["tasks"]) == 1
                assert result["tasks"][0]["name"] == "my_project.build"
                assert "types" in result
                assert len(result["types"]) == 1
                assert result["types"][0]["name"] == "my_project.MyType"
                assert "skills" in result
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())


class TestValidateCommand:
    """Tests for validate command"""
    
    def test_validate_returns_valid_for_good_config(self, tmp_path):
        """Test validate returns valid=true for good configuration"""
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

        async def _run():
            server = DfmCommandServer(runner=MockRunner(), builder=MockBuilder())
            await server.start()
            try:
                client = DfmClient(server.socket_path)
                result = await client.validate()
                assert result["valid"] == True
                assert result["error_count"] == 0
                assert result["errors"] == []
            finally:
                await client.disconnect()
                await server.stop()

        asyncio.run(_run())


class TestClientMode:
    """Tests for dfm client mode (DFM_SERVER_SOCKET)"""
    
    def test_client_mode_detected(self, tmp_path, monkeypatch):
        """Test that dfm detects client mode from environment"""
        import subprocess
        import sys
        
        # This test verifies the environment variable detection
        # We can't easily test the full client mode without a running server
        
        # Set environment variable
        socket_path = str(tmp_path / "test.sock")
        
        # Run dfm with DFM_SERVER_SOCKET set and expect connection error
        result = subprocess.run(
            [sys.executable, "-m", "dv_flow.mgr", "ping"],
            env={**os.environ, "DFM_SERVER_SOCKET": socket_path},
            capture_output=True,
            text=True
        )
        
        # Should have error in stderr about socket not found
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()
