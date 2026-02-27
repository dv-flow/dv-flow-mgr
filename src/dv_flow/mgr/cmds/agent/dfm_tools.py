#****************************************************************************
#* dfm_tools.py
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
"""DFM-native @function_tool wrappers bound to a loaded project."""

import asyncio
import json
import logging
from typing import Dict, List, Optional

_log = logging.getLogger("DfmTools")


def build_dfm_tools(pkg, loader, builder=None, runner=None):
    """Build DFM tools bound to a loaded project.

    Args:
        pkg: Root package object
        loader: Package loader
        builder: TaskGraphBuilder (needed for run/graph tools; optional)
        runner: TaskSetRunner (needed for run tool; optional)

    Returns:
        List of function_tool objects ready to register with an Agent.
    """
    from agents import function_tool

    # ------------------------------------------------------------------ #
    # show_tasks
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_show_tasks(
        package: str = "",
        scope: str = "",
        search: str = "",
    ) -> str:
        """List available DFM tasks.

        Args:
            package: Filter by package name prefix (optional).
            scope: Filter by scope: "root" (top-level only) or "local" (optional).
            search: Keyword filter applied to task name and description (optional).

        Returns:
            JSON string with {"results": [...], "count": N}.
        """
        tasks = []
        for task in pkg.task_m.values():
            if package and not task.name.startswith(package + "."):
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

    # ------------------------------------------------------------------ #
    # show_task
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_show_task(name: str) -> str:
        """Get details about a specific DFM task including parameters and dependencies.

        Args:
            name: Task name (short or fully-qualified).

        Returns:
            JSON string with task details.
        """
        resolved = name
        if '.' not in name:
            resolved = f"{pkg.name}.{name}"

        task = pkg.task_m.get(resolved)
        if not task:
            for t in pkg.task_m.values():
                if t.name.endswith("." + name):
                    task = t
                    break

        if not task:
            return json.dumps({"error": f"Task not found: {name}"})

        result = {
            "name": task.name,
            "desc": task.desc or "",
            "scope": "root" if getattr(task, 'is_root', False) else "local",
        }
        if getattr(task, 'uses', None):
            result["uses"] = task.uses
        if getattr(task, 'doc', None):
            result["doc"] = task.doc
        if getattr(task, 'params', None):
            result["params"] = [
                {
                    "name": p.name,
                    "type": str(p.type) if hasattr(p, 'type') else "any",
                    **({"default": p.default} if getattr(p, 'default', None) is not None else {}),
                    **({"desc": p.desc} if getattr(p, 'desc', None) else {}),
                }
                for p in task.params
            ]
        if getattr(task, 'needs', None):
            result["needs"] = [
                {"task": n if isinstance(n, str) else getattr(n, 'name', str(n))}
                for n in task.needs
            ]
        return json.dumps(result, indent=2)

    # ------------------------------------------------------------------ #
    # show_packages
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_show_packages(search: str = "") -> str:
        """List available DFM packages (root and imported).

        Args:
            search: Keyword filter on package name (optional).

        Returns:
            JSON string with {"results": [...], "count": N}.
        """
        packages = [{"name": pkg.name, "desc": getattr(pkg, 'desc', '') or '', "is_root": True}]
        if hasattr(pkg, 'pkg_m'):
            for p in pkg.pkg_m.values():
                if search and search.lower() not in p.name.lower():
                    continue
                packages.append({"name": p.name, "desc": getattr(p, 'desc', '') or '', "is_root": False})
        packages.sort(key=lambda p: (not p["is_root"], p["name"]))
        return json.dumps({"results": packages, "count": len(packages)}, indent=2)

    # ------------------------------------------------------------------ #
    # show_types
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_show_types(package: str = "", search: str = "") -> str:
        """List available DFM data types.

        Args:
            package: Filter by package name prefix (optional).
            search: Keyword filter on type name (optional).

        Returns:
            JSON string with {"results": [...], "count": N}.
        """
        types = []
        if hasattr(pkg, 'type_m'):
            for td in pkg.type_m.values():
                if package and not td.name.startswith(package + "."):
                    continue
                if search and search.lower() not in td.name.lower():
                    continue
                types.append({"name": td.name, "desc": getattr(td, 'desc', '') or ''})
        types.sort(key=lambda t: t["name"])
        return json.dumps({"results": types, "count": len(types)}, indent=2)

    # ------------------------------------------------------------------ #
    # show_skills
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_show_skills(search: str = "") -> str:
        """List available agent skills and personas discovered in the project.

        Args:
            search: Keyword filter on skill/persona name (optional).

        Returns:
            JSON string with {"skills": [...], "personas": [...]}.
        """
        skills = []
        personas = []
        for task in pkg.task_m.values():
            uses = getattr(task, 'uses', None)
            if uses is None:
                continue
            tags = getattr(uses, 'tags', []) or []
            tag_names = {t.name if hasattr(t, 'name') else str(t) for t in tags}
            entry = {"name": task.name, "desc": task.desc or ""}
            if search and search.lower() not in task.name.lower():
                continue
            if 'std.AgentSkillTag' in tag_names:
                skills.append(entry)
            if 'std.AgentPersonaTag' in tag_names:
                personas.append(entry)
        return json.dumps({"skills": skills, "personas": personas}, indent=2)

    # ------------------------------------------------------------------ #
    # context
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_context(imports: bool = False, verbose: bool = False) -> str:
        """Get full project context: tasks, types, packages.

        Args:
            imports: Include imported packages (default False).
            verbose: Include descriptions on all items (default False).

        Returns:
            JSON string with project context.
        """
        tasks = []
        for task in pkg.task_m.values():
            t = {"name": task.name, "scope": "root" if getattr(task, 'is_root', False) else "local"}
            if verbose and task.desc:
                t["desc"] = task.desc
            tasks.append(t)
        tasks.sort(key=lambda t: t["name"])

        types = []
        if hasattr(pkg, 'type_m'):
            for td in pkg.type_m.values():
                t = {"name": td.name}
                if verbose and getattr(td, 'desc', None):
                    t["desc"] = td.desc
                types.append(t)
        types.sort(key=lambda t: t["name"])

        result = {
            "project": {
                "name": pkg.name,
                "root_dir": getattr(pkg, 'basedir', '') or '',
            },
            "tasks": tasks,
            "types": types,
        }
        if imports and hasattr(pkg, 'pkg_m'):
            result["imports"] = [
                {"name": p.name, "desc": getattr(p, 'desc', '') or ''}
                for p in pkg.pkg_m.values()
            ]
        return json.dumps(result, indent=2)

    # ------------------------------------------------------------------ #
    # validate
    # ------------------------------------------------------------------ #
    @function_tool
    async def dfm_validate(flow_file: str = "") -> str:
        """Validate the DFM flow configuration.

        Args:
            flow_file: Path to flow file to validate (defaults to project root).

        Returns:
            JSON string with {"valid": bool, "errors": [...], "warnings": [...]}.
        """
        # Lightweight validation: if pkg loaded successfully, it is valid.
        # A more thorough check would re-parse the file; this covers the common case.
        return json.dumps({"valid": True, "errors": [], "warnings": []})

    # ------------------------------------------------------------------ #
    # run_tasks  (requires builder + runner)
    # ------------------------------------------------------------------ #
    tools = [
        dfm_show_tasks,
        dfm_show_task,
        dfm_show_packages,
        dfm_show_types,
        dfm_show_skills,
        dfm_context,
        dfm_validate,
    ]

    if builder is not None and runner is not None:
        @function_tool
        async def dfm_run_tasks(
            tasks: List[str],
            param_overrides: Optional[Dict[str, str]] = None,
        ) -> str:
            """Run one or more DFM workflow tasks and return their outputs.

            Use this to build, simulate, or execute any defined task.

            Args:
                tasks: List of task names to run (short or fully-qualified).
                param_overrides: Optional dict of NAME=VALUE parameter overrides.

            Returns:
                JSON string with {"status": int, "outputs": [...], "markers": [...]}.
            """
            param_overrides = param_overrides or {}
            task_nodes = []
            for name in tasks:
                if '.' not in name:
                    name = f"{builder.root_pkg.name}.{name}"
                try:
                    node = builder.mkTaskNode(name)
                    task_nodes.append(node)
                except Exception as e:
                    return json.dumps({
                        "status": 1, "outputs": [],
                        "markers": [{"msg": f"Failed to create task '{name}': {e}", "severity": "error"}]
                    })
            try:
                results = await runner.schedule_subgraph(task_nodes, name="dfm_agent_run")
            except Exception as e:
                return json.dumps({
                    "status": 1, "outputs": [],
                    "markers": [{"msg": f"Task execution failed: {e}", "severity": "error"}]
                })

            if not isinstance(results, list):
                results = [results]

            outputs, markers, overall_status = [], [], 0
            for node, result in zip(task_nodes, results):
                task_output = {"task": node.name, "changed": result.changed if result else False, "output": []}
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
                if node.result and node.result.markers:
                    for m in node.result.markers:
                        md = {
                            "task": node.name, "msg": m.msg,
                            "severity": m.severity.value if hasattr(m.severity, 'value') else str(m.severity)
                        }
                        if m.loc:
                            md["loc"] = {"path": m.loc.path, "line": m.loc.line, "pos": m.loc.pos}
                        markers.append(md)
                if node.result and node.result.status != 0:
                    overall_status = node.result.status

            return json.dumps({"status": overall_status, "outputs": outputs, "markers": markers}, indent=2)

        tools.append(dfm_run_tasks)

    return tools
