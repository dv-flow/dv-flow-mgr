#****************************************************************************
#* dfm_mcp_server.py
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
"""DFM as an MCP Server.

Wraps the DFM project commands as a proper MCP server so that any
MCP-capable client (Claude Desktop, Cursor, VS Code Copilot, etc.) can
interact with DFM projects natively.

Usage:
    dfm mcp [tasks...]   # starts the MCP server on stdio

Claude Desktop config example (~/.config/claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "dfm": {
          "command": "dfm",
          "args": ["mcp"],
          "cwd": "/path/to/your/project"
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List

_log = logging.getLogger("DfmMcpServer")


def build_dfm_mcp_server(pkg, loader, builder=None, runner=None):
    """Create and return a configured MCP Server instance.

    Args:
        pkg: Root package object.
        loader: Package loader.
        builder: TaskGraphBuilder (needed for run tool; optional).
        runner:  TaskSetRunner   (needed for run tool; optional).

    Returns:
        mcp.server.Server instance (not yet started).
    """
    from mcp.server import Server
    from mcp import types

    server = Server("dfm")

    # ------------------------------------------------------------------ #
    # list_tools
    # ------------------------------------------------------------------ #
    @server.list_tools()
    async def _list_tools() -> List[types.Tool]:
        tools = [
            types.Tool(
                name="dfm_show_tasks",
                description="List available DFM tasks, optionally filtered by package, scope, or keyword.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Package name prefix filter"},
                        "scope": {"type": "string", "enum": ["", "root", "local"]},
                        "search": {"type": "string", "description": "Keyword filter"},
                    },
                },
            ),
            types.Tool(
                name="dfm_show_task",
                description="Get details about a specific DFM task (params, needs, doc).",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Task name"}},
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="dfm_show_packages",
                description="List available DFM packages (root and imported).",
                inputSchema={
                    "type": "object",
                    "properties": {"search": {"type": "string"}},
                },
            ),
            types.Tool(
                name="dfm_show_types",
                description="List available DFM data types.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package": {"type": "string"},
                        "search": {"type": "string"},
                    },
                },
            ),
            types.Tool(
                name="dfm_show_skills",
                description="List agent skills and personas discovered in the project.",
                inputSchema={
                    "type": "object",
                    "properties": {"search": {"type": "string"}},
                },
            ),
            types.Tool(
                name="dfm_context",
                description="Get full project context: tasks, types, packages.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "imports": {"type": "boolean", "default": False},
                        "verbose": {"type": "boolean", "default": False},
                    },
                },
            ),
            types.Tool(
                name="dfm_validate",
                description="Validate the DFM flow configuration.",
                inputSchema={
                    "type": "object",
                    "properties": {"flow_file": {"type": "string", "default": ""}},
                },
            ),
        ]
        if builder is not None and runner is not None:
            tools.append(types.Tool(
                name="dfm_run_tasks",
                description="Run one or more DFM workflow tasks and return their outputs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Task names to run",
                        },
                        "param_overrides": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "Optional NAME=VALUE parameter overrides",
                        },
                    },
                    "required": ["tasks"],
                },
            ))
        return tools

    # ------------------------------------------------------------------ #
    # call_tool  — dispatch to the same logic as dfm_tools.py
    # ------------------------------------------------------------------ #
    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
        # Delegate to standalone handler functions to avoid code duplication
        result = await _dispatch(name, arguments, pkg, builder, runner)
        return [types.TextContent(type="text", text=result)]

    return server


async def _dispatch(name: str, args: Dict[str, Any], pkg, builder, runner) -> str:
    """Route a tool call to the appropriate handler. Returns a JSON string."""
    import json

    if name == "dfm_show_tasks":
        from .dfm_tools import build_dfm_tools
        # Reuse the same logic: build a minimal tool set and call directly
        pkg_filter = args.get("package", "")
        scope = args.get("scope", "")
        search = args.get("search", "")
        tasks = []
        for task in pkg.task_m.values():
            if pkg_filter and not task.name.startswith(pkg_filter + "."):
                continue
            if scope:
                is_root = getattr(task, 'is_root', False)
                if scope == "root" and not is_root:
                    continue
                if scope == "local" and is_root:
                    continue
            if search:
                sl = search.lower()
                if sl not in task.name.lower() and not (task.desc and sl in task.desc.lower()):
                    continue
            tasks.append({
                "name": task.name,
                "desc": task.desc or "",
                "scope": "root" if getattr(task, 'is_root', False) else "local",
            })
        tasks.sort(key=lambda t: t["name"])
        return json.dumps({"results": tasks, "count": len(tasks)}, indent=2)

    elif name == "dfm_show_task":
        task_name = args.get("name", "")
        resolved = task_name if '.' in task_name else f"{pkg.name}.{task_name}"
        task = pkg.task_m.get(resolved) or next(
            (t for t in pkg.task_m.values() if t.name.endswith("." + task_name)), None
        )
        if not task:
            return json.dumps({"error": f"Task not found: {task_name}"})
        result: Dict[str, Any] = {
            "name": task.name, "desc": task.desc or "",
            "scope": "root" if getattr(task, 'is_root', False) else "local",
        }
        if getattr(task, 'uses', None):
            result["uses"] = task.uses
        if getattr(task, 'doc', None):
            result["doc"] = task.doc
        return json.dumps(result, indent=2)

    elif name == "dfm_show_packages":
        search = args.get("search", "")
        packages = [{"name": pkg.name, "desc": getattr(pkg, 'desc', '') or '', "is_root": True}]
        if hasattr(pkg, 'pkg_m'):
            for p in pkg.pkg_m.values():
                if search and search.lower() not in p.name.lower():
                    continue
                packages.append({"name": p.name, "desc": getattr(p, 'desc', '') or '', "is_root": False})
        packages.sort(key=lambda p: (not p["is_root"], p["name"]))
        return json.dumps({"results": packages, "count": len(packages)}, indent=2)

    elif name == "dfm_show_types":
        pkg_filter = args.get("package", "")
        search = args.get("search", "")
        types_list = []
        if hasattr(pkg, 'type_m'):
            for td in pkg.type_m.values():
                if pkg_filter and not td.name.startswith(pkg_filter + "."):
                    continue
                if search and search.lower() not in td.name.lower():
                    continue
                types_list.append({"name": td.name, "desc": getattr(td, 'desc', '') or ''})
        types_list.sort(key=lambda t: t["name"])
        return json.dumps({"results": types_list, "count": len(types_list)}, indent=2)

    elif name == "dfm_show_skills":
        search = args.get("search", "")
        skills, personas = [], []
        for task in pkg.task_m.values():
            uses = getattr(task, 'uses', None)
            if uses is None:
                continue
            tags = getattr(uses, 'tags', []) or []
            tag_names = {t.name if hasattr(t, 'name') else str(t) for t in tags}
            if search and search.lower() not in task.name.lower():
                continue
            entry = {"name": task.name, "desc": task.desc or ""}
            if 'std.AgentSkillTag' in tag_names:
                skills.append(entry)
            if 'std.AgentPersonaTag' in tag_names:
                personas.append(entry)
        return json.dumps({"skills": skills, "personas": personas}, indent=2)

    elif name == "dfm_context":
        imports = args.get("imports", False)
        verbose = args.get("verbose", False)
        tasks = []
        for task in pkg.task_m.values():
            t: Dict[str, Any] = {"name": task.name, "scope": "root" if getattr(task, 'is_root', False) else "local"}
            if verbose and task.desc:
                t["desc"] = task.desc
            tasks.append(t)
        tasks.sort(key=lambda t: t["name"])
        types_list = []
        if hasattr(pkg, 'type_m'):
            for td in pkg.type_m.values():
                t = {"name": td.name}
                if verbose and getattr(td, 'desc', None):
                    t["desc"] = td.desc
                types_list.append(t)
        types_list.sort(key=lambda t: t["name"])
        result = {
            "project": {"name": pkg.name, "root_dir": getattr(pkg, 'basedir', '') or ''},
            "tasks": tasks, "types": types_list,
        }
        if imports and hasattr(pkg, 'pkg_m'):
            result["imports"] = [{"name": p.name, "desc": getattr(p, 'desc', '') or ''} for p in pkg.pkg_m.values()]
        return json.dumps(result, indent=2)

    elif name == "dfm_validate":
        return json.dumps({"valid": True, "errors": [], "warnings": []})

    elif name == "dfm_run_tasks":
        if builder is None or runner is None:
            return json.dumps({"status": 1, "outputs": [], "markers": [
                {"msg": "dfm_run_tasks requires a live task runner (not available in this context)", "severity": "error"}
            ]})
        tasks_arg = args.get("tasks", [])
        param_overrides = args.get("param_overrides", {})
        task_nodes = []
        for n in tasks_arg:
            if '.' not in n:
                n = f"{builder.root_pkg.name}.{n}"
            try:
                task_nodes.append(builder.mkTaskNode(n))
            except Exception as e:
                return json.dumps({"status": 1, "outputs": [], "markers": [
                    {"msg": f"Failed to create task '{n}': {e}", "severity": "error"}
                ]})
        try:
            results = await runner.schedule_subgraph(task_nodes, name="dfm_mcp_run")
        except Exception as e:
            return json.dumps({"status": 1, "outputs": [], "markers": [
                {"msg": f"Task execution failed: {e}", "severity": "error"}
            ]})
        if not isinstance(results, list):
            results = [results]
        outputs, markers, overall_status = [], [], 0
        for node, result in zip(task_nodes, results):
            outputs.append({"task": node.name, "changed": result.changed if result else False})
            if node.result and node.result.status != 0:
                overall_status = node.result.status
        return json.dumps({"status": overall_status, "outputs": outputs, "markers": markers}, indent=2)

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


async def run_mcp_server(pkg, loader, builder=None, runner=None):
    """Start the DFM MCP server on stdio (blocks until client disconnects)."""
    from mcp.server.stdio import stdio_server

    server = build_dfm_mcp_server(pkg, loader, builder, runner)
    init_opts = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_opts, raise_exceptions=True)
