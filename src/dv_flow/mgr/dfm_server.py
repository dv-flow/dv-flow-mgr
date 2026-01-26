#****************************************************************************
#* dfm_server.py
#*
#* DFM Command Server - Handles JSON-RPC requests from LLM assistant processes
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
DFM Command Server for LLM Call Interface

This module implements a JSON-RPC server over Unix sockets that allows
LLM assistant processes (running within Prompt tasks) to execute DFM
commands within the context of the parent TaskSetRunner session.

Key features:
- Shares resource management (exec_semaphore) with parent session
- Provides access to task outputs from completed tasks
- Supports dynamic task scheduling via DynamicScheduler
- Returns structured JSON responses for LLM consumption
"""

import asyncio
import json
import logging
import os
import stat
import tempfile
import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .task_runner import TaskSetRunner
    from .task_graph_builder import TaskGraphBuilder

_log = logging.getLogger("DfmServer")


# JSON-RPC error codes
class JsonRpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Custom error codes
    TASK_EXECUTION_FAILED = -32000
    TASK_NOT_FOUND = -32001
    VALIDATION_FAILED = -32002
    TIMEOUT = -32003


class DfmCommandServer:
    """
    JSON-RPC server for DFM commands over Unix socket.
    
    This server runs within the TaskSetRunner context and handles
    requests from LLM assistant processes to execute tasks, query
    project state, and validate configurations.
    """
    
    def __init__(
        self,
        runner: 'TaskSetRunner',
        builder: 'TaskGraphBuilder',
        socket_path: Optional[str] = None
    ):
        """
        Initialize the command server.
        
        Args:
            runner: The TaskSetRunner instance managing task execution
            builder: The TaskGraphBuilder for creating task nodes
            socket_path: Path for Unix socket (auto-generated if None)
        """
        self.runner = runner
        self.builder = builder
        self.socket_path = socket_path or self._generate_socket_path()
        self._server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[str, Callable] = {}
        self._request_id = 0
        self._running = False
        
        # Register command handlers
        self._register_handlers()
    
    def _generate_socket_path(self) -> str:
        """Generate a unique socket path in temp directory"""
        session_id = uuid.uuid4().hex[:8]
        return os.path.join(tempfile.gettempdir(), f"dfm-{session_id}.sock")
    
    def _register_handlers(self):
        """Register all command handlers"""
        self._handlers = {
            "run": self._handle_run,
            "show.tasks": self._handle_show_tasks,
            "show.task": self._handle_show_task,
            "show.types": self._handle_show_types,
            "show.packages": self._handle_show_packages,
            "context": self._handle_context,
            "validate": self._handle_validate,
            "ping": self._handle_ping,
        }
    
    async def start(self):
        """Start the command server"""
        if self._running:
            _log.warning("Server already running")
            return
        
        # Remove existing socket if present
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        # Create Unix socket server
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path
        )
        
        # Set socket permissions to owner only (0600)
        os.chmod(self.socket_path, stat.S_IRUSR | stat.S_IWUSR)
        
        self._running = True
        _log.info(f"DFM command server started at {self.socket_path}")
    
    async def stop(self):
        """Stop the command server"""
        if not self._running:
            return
        
        self._running = False
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        # Clean up socket file
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
        
        _log.info("DFM command server stopped")
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        """Handle a client connection"""
        client_addr = writer.get_extra_info('peername')
        _log.debug(f"Client connected: {client_addr}")
        
        try:
            while self._running:
                # Read message (newline-delimited JSON)
                try:
                    line = await asyncio.wait_for(
                        reader.readline(),
                        timeout=300.0  # 5 minute timeout per request
                    )
                except asyncio.TimeoutError:
                    _log.warning("Client read timeout")
                    break
                
                if not line:
                    break
                
                # Parse and handle request
                try:
                    request = json.loads(line.decode('utf-8'))
                    response = await self._handle_request(request)
                except json.JSONDecodeError as e:
                    response = self._error_response(
                        None,
                        JsonRpcError.PARSE_ERROR,
                        f"Parse error: {str(e)}"
                    )
                
                # Send response
                response_bytes = (json.dumps(response) + "\n").encode('utf-8')
                writer.write(response_bytes)
                await writer.drain()
                
        except Exception as e:
            _log.error(f"Error handling client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            _log.debug(f"Client disconnected: {client_addr}")
    
    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request"""
        # Validate request structure
        if not isinstance(request, dict):
            return self._error_response(
                None,
                JsonRpcError.INVALID_REQUEST,
                "Request must be a JSON object"
            )
        
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        
        if not method:
            return self._error_response(
                request_id,
                JsonRpcError.INVALID_REQUEST,
                "Missing 'method' field"
            )
        
        # Find handler
        handler = self._handlers.get(method)
        if not handler:
            return self._error_response(
                request_id,
                JsonRpcError.METHOD_NOT_FOUND,
                f"Unknown method: {method}"
            )
        
        # Execute handler
        try:
            _log.debug(f"Handling request: method={method}, params={params}")
            result = await handler(params)
            return self._success_response(request_id, result)
        except Exception as e:
            _log.exception(f"Error handling {method}")
            return self._error_response(
                request_id,
                JsonRpcError.INTERNAL_ERROR,
                str(e)
            )
    
    def _success_response(
        self,
        request_id: Any,
        result: Any
    ) -> Dict[str, Any]:
        """Create a success response"""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
    
    def _error_response(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: Any = None
    ) -> Dict[str, Any]:
        """Create an error response"""
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error
        }
    
    # =========================================================================
    # Command Handlers
    # =========================================================================
    
    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request - used for health checks"""
        return {"status": "ok", "server": "dfm"}
    
    async def _handle_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle run request - execute tasks and return their outputs.
        
        Params:
            tasks: List of task names to run
            param_overrides: Optional dict of parameter overrides
            timeout: Optional timeout in seconds
        """
        task_names = params.get("tasks", [])
        param_overrides = params.get("param_overrides", {})
        timeout = params.get("timeout")
        
        if not task_names:
            raise ValueError("No tasks specified")
        
        if isinstance(task_names, str):
            task_names = [task_names]
        
        _log.info(f"Running tasks: {task_names}")
        
        # Build task nodes
        task_nodes = []
        for name in task_names:
            # Resolve task name (add package prefix if needed)
            if '.' not in name:
                name = f"{self.builder.root_pkg.name}.{name}"
            
            try:
                node = self.builder.mkTaskNode(name)
                task_nodes.append(node)
            except Exception as e:
                return {
                    "status": 1,
                    "outputs": [],
                    "markers": [
                        {"msg": f"Failed to create task '{name}': {str(e)}", "severity": "error"}
                    ]
                }
        
        # Schedule tasks using DynamicScheduler
        try:
            if timeout:
                results = await self.runner.schedule_subgraph(
                    task_nodes,
                    name="dfm_server_run",
                    timeout=timeout
                )
            else:
                results = await self.runner.schedule_subgraph(
                    task_nodes,
                    name="dfm_server_run"
                )
        except asyncio.TimeoutError:
            return {
                "status": 1,
                "outputs": [],
                "markers": [
                    {"msg": f"Task execution timed out after {timeout}s", "severity": "error"}
                ]
            }
        except Exception as e:
            _log.exception("Task execution failed")
            return {
                "status": 1,
                "outputs": [],
                "markers": [
                    {"msg": f"Task execution failed: {str(e)}", "severity": "error"}
                ]
            }
        
        # Format results
        if not isinstance(results, list):
            results = [results]
        
        outputs = []
        markers = []
        overall_status = 0
        
        for i, (node, result) in enumerate(zip(task_nodes, results)):
            task_output = {
                "task": node.name,
                "changed": result.changed if result else False,
                "output": []
            }
            
            if result and result.output:
                for item in result.output:
                    if hasattr(item, 'model_dump'):
                        task_output["output"].append(item.model_dump())
                    elif hasattr(item, '__dict__'):
                        task_output["output"].append(
                            {k: v for k, v in item.__dict__.items() if not k.startswith('_')}
                        )
                    else:
                        task_output["output"].append(str(item))
            
            outputs.append(task_output)
            
            # Collect markers from task result
            if node.result and node.result.markers:
                for marker in node.result.markers:
                    marker_dict = {
                        "task": node.name,
                        "msg": marker.msg,
                        "severity": marker.severity.value if hasattr(marker.severity, 'value') else str(marker.severity)
                    }
                    if marker.loc:
                        marker_dict["loc"] = {
                            "path": marker.loc.path,
                            "line": marker.loc.line,
                            "pos": marker.loc.pos
                        }
                    markers.append(marker_dict)
            
            # Check task status
            if node.result and node.result.status != 0:
                overall_status = node.result.status
        
        return {
            "status": overall_status,
            "outputs": outputs,
            "markers": markers
        }
    
    async def _handle_show_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle show.tasks request - list available tasks"""
        package_filter = params.get("package")
        scope_filter = params.get("scope")
        search = params.get("search")
        
        tasks = []
        
        # Collect tasks from root package
        root_pkg = self.builder.root_pkg
        for task in root_pkg.task_m.values():
            # Apply filters
            if package_filter and not task.name.startswith(package_filter + "."):
                continue
            
            if scope_filter:
                is_root = getattr(task, 'is_root', False)
                if scope_filter == "root" and not is_root:
                    continue
                if scope_filter == "local" and is_root:
                    continue
            
            if search:
                search_lower = search.lower()
                name_match = search_lower in task.name.lower()
                desc_match = task.desc and search_lower in task.desc.lower()
                if not (name_match or desc_match):
                    continue
            
            task_info = {
                "name": task.name,
                "desc": task.desc or "",
                "scope": "root" if getattr(task, 'is_root', False) else "local"
            }
            
            if hasattr(task, 'uses') and task.uses:
                task_info["uses"] = task.uses
            
            tasks.append(task_info)
        
        # Sort by name
        tasks.sort(key=lambda t: t["name"])
        
        return {
            "results": tasks,
            "count": len(tasks)
        }
    
    async def _handle_show_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle show.task request - get details about a specific task"""
        name = params.get("name")
        if not name:
            raise ValueError("Task name required")
        
        # Resolve task name
        if '.' not in name:
            name = f"{self.builder.root_pkg.name}.{name}"
        
        root_pkg = self.builder.root_pkg
        task = root_pkg.task_m.get(name)
        
        if not task:
            # Try without package prefix
            for t in root_pkg.task_m.values():
                if t.name == name or t.name.endswith("." + name):
                    task = t
                    break
        
        if not task:
            raise ValueError(f"Task not found: {name}")
        
        result = {
            "name": task.name,
            "desc": task.desc or "",
            "scope": "root" if getattr(task, 'is_root', False) else "local"
        }
        
        if hasattr(task, 'uses') and task.uses:
            result["uses"] = task.uses
        
        if hasattr(task, 'doc') and task.doc:
            result["doc"] = task.doc
        
        # Get parameters
        if hasattr(task, 'params') and task.params:
            params_list = []
            for pdef in task.params:
                param_info = {
                    "name": pdef.name,
                    "type": str(pdef.type) if hasattr(pdef, 'type') else "any"
                }
                if hasattr(pdef, 'default') and pdef.default is not None:
                    param_info["default"] = pdef.default
                if hasattr(pdef, 'desc') and pdef.desc:
                    param_info["desc"] = pdef.desc
                params_list.append(param_info)
            result["params"] = params_list
        
        # Get needs
        if hasattr(task, 'needs') and task.needs:
            needs_list = []
            for need in task.needs:
                if isinstance(need, str):
                    needs_list.append({"task": need})
                elif hasattr(need, 'name'):
                    needs_list.append({"task": need.name})
            result["needs"] = needs_list
        
        return result
    
    async def _handle_show_types(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle show.types request - list available data types"""
        package_filter = params.get("package")
        search = params.get("search")
        
        types = []
        
        root_pkg = self.builder.root_pkg
        if hasattr(root_pkg, 'type_m'):
            for type_def in root_pkg.type_m.values():
                # Apply filters
                if package_filter and not type_def.name.startswith(package_filter + "."):
                    continue
                
                if search:
                    search_lower = search.lower()
                    if search_lower not in type_def.name.lower():
                        continue
                
                type_info = {
                    "name": type_def.name,
                    "desc": getattr(type_def, 'desc', "") or ""
                }
                types.append(type_info)
        
        types.sort(key=lambda t: t["name"])
        
        return {
            "results": types,
            "count": len(types)
        }
    
    async def _handle_show_packages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle show.packages request - list available packages"""
        search = params.get("search")
        
        packages = []
        
        root_pkg = self.builder.root_pkg
        
        # Add root package
        pkg_info = {
            "name": root_pkg.name,
            "desc": getattr(root_pkg, 'desc', "") or "",
            "is_root": True
        }
        packages.append(pkg_info)
        
        # Add imported packages
        if hasattr(root_pkg, 'pkg_m'):
            for pkg in root_pkg.pkg_m.values():
                if search and search.lower() not in pkg.name.lower():
                    continue
                
                pkg_info = {
                    "name": pkg.name,
                    "desc": getattr(pkg, 'desc', "") or "",
                    "is_root": False
                }
                packages.append(pkg_info)
        
        packages.sort(key=lambda p: (not p["is_root"], p["name"]))
        
        return {
            "results": packages,
            "count": len(packages)
        }
    
    async def _handle_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle context request - get full project context"""
        include_imports = params.get("imports", False)
        verbose = params.get("verbose", False)
        
        root_pkg = self.builder.root_pkg
        
        # Project info
        project = {
            "name": root_pkg.name,
            "root_dir": getattr(root_pkg, 'basedir', "") or "",
            "rundir": self.runner.rundir
        }
        
        # Tasks
        tasks = []
        for task in root_pkg.task_m.values():
            task_info = {
                "name": task.name,
                "scope": "root" if getattr(task, 'is_root', False) else "local"
            }
            if hasattr(task, 'uses') and task.uses:
                task_info["uses"] = task.uses
            if hasattr(task, 'desc') and task.desc:
                task_info["desc"] = task.desc
            tasks.append(task_info)
        tasks.sort(key=lambda t: t["name"])
        
        # Types
        types = []
        if hasattr(root_pkg, 'type_m'):
            for type_def in root_pkg.type_m.values():
                type_info = {"name": type_def.name}
                if verbose and hasattr(type_def, 'desc') and type_def.desc:
                    type_info["desc"] = type_def.desc
                types.append(type_info)
        types.sort(key=lambda t: t["name"])
        
        # Skills (types tagged with AgentSkillTag)
        skills = []
        # This would need access to the skill registry - simplified for now
        
        result = {
            "project": project,
            "tasks": tasks,
            "types": types,
            "skills": skills
        }
        
        # Include imported packages if requested
        if include_imports and hasattr(root_pkg, 'pkg_m'):
            imports = []
            for pkg in root_pkg.pkg_m.values():
                imports.append({
                    "name": pkg.name,
                    "desc": getattr(pkg, 'desc', "") or ""
                })
            result["imports"] = imports
        
        return result
    
    async def _handle_validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle validate request - validate a flow configuration"""
        flow_file = params.get("file")
        
        # For now, return validation result based on current project state
        # Full validation would require loading and checking the specified file
        
        errors = []
        warnings = []
        
        root_pkg = self.builder.root_pkg
        
        # Check for undefined task references in needs
        for task in root_pkg.task_m.values():
            if hasattr(task, 'needs') and task.needs:
                for need in task.needs:
                    need_name = need if isinstance(need, str) else getattr(need, 'name', str(need))
                    # Resolve full name
                    if '.' not in need_name:
                        need_name = f"{root_pkg.name}.{need_name}"
                    
                    if need_name not in root_pkg.task_m:
                        errors.append({
                            "type": "UndefinedTask",
                            "message": f"Task '{task.name}' references undefined task '{need_name}'",
                            "location": {"task": task.name}
                        })
        
        return {
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings
        }


class DfmClient:
    """
    Client for communicating with DFM command server.
    
    This class is used by the dfm CLI when DFM_SERVER_SOCKET is set,
    forwarding commands to the parent session's server.
    """
    
    def __init__(self, socket_path: str):
        """
        Initialize the client.
        
        Args:
            socket_path: Path to the Unix socket
        """
        self.socket_path = socket_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0
    
    async def connect(self):
        """Connect to the server"""
        if not os.path.exists(self.socket_path):
            raise ConnectionError(f"Server socket not found: {self.socket_path}")
        
        self._reader, self._writer = await asyncio.open_unix_connection(
            self.socket_path
        )
        _log.debug(f"Connected to server at {self.socket_path}")
    
    async def disconnect(self):
        """Disconnect from the server"""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None
    
    async def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """
        Call a server method.
        
        Args:
            method: The method name to call
            params: Optional parameters
            timeout: Request timeout in seconds
            
        Returns:
            The result from the server
            
        Raises:
            Exception: If the server returns an error
        """
        if not self._writer:
            await self.connect()
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }
        
        # Send request
        request_bytes = (json.dumps(request) + "\n").encode('utf-8')
        self._writer.write(request_bytes)
        await self._writer.drain()
        
        # Read response
        try:
            line = await asyncio.wait_for(
                self._reader.readline(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Server request timed out after {timeout}s")
        
        if not line:
            raise ConnectionError("Server closed connection")
        
        response = json.loads(line.decode('utf-8'))
        
        # Check for error
        if "error" in response:
            error = response["error"]
            raise Exception(f"Server error ({error['code']}): {error['message']}")
        
        return response.get("result", {})
    
    async def run(
        self,
        tasks: List[str],
        param_overrides: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Run tasks on the server"""
        params = {"tasks": tasks}
        if param_overrides:
            params["param_overrides"] = param_overrides
        if timeout:
            params["timeout"] = timeout
        
        return await self.call("run", params)
    
    async def show_tasks(
        self,
        package: Optional[str] = None,
        scope: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """List tasks"""
        params = {}
        if package:
            params["package"] = package
        if scope:
            params["scope"] = scope
        if search:
            params["search"] = search
        
        return await self.call("show.tasks", params)
    
    async def show_task(self, name: str) -> Dict[str, Any]:
        """Get task details"""
        return await self.call("show.task", {"name": name})
    
    async def context(
        self,
        include_imports: bool = False,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Get project context"""
        return await self.call("context", {
            "imports": include_imports,
            "verbose": verbose
        })
    
    async def validate(self, file: Optional[str] = None) -> Dict[str, Any]:
        """Validate flow configuration"""
        params = {}
        if file:
            params["file"] = file
        return await self.call("validate", params)
    
    async def ping(self) -> Dict[str, Any]:
        """Health check"""
        return await self.call("ping")
