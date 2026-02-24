#****************************************************************************
#* mcp_setup.py
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
"""MCP server lifecycle management.

Builds a list of MCPServerStdio/MCPServerSse instances for the agent:

1. Built-in mcp-shell-server (via uvx) — shell execution
2. Built-in @modelcontextprotocol/server-filesystem (via npx) — file ops
3. User-defined MCP servers from AgentTool tasks in flow.yaml

Falls back gracefully when external tools (uvx, npx) are not available.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .context_builder import AgentContext

_log = logging.getLogger("McpSetup")

# Shell commands to allow when mcp-shell-server is used
_SHELL_ALLOW = "bash,python,python3,pip,git,rg,cat,ls,find,grep,sed,awk,head,tail,wc,dfm,make"


def build_mcp_servers(
    context: Optional["AgentContext"],
    working_dir: Optional[str] = None,
    enable_shell: Optional[bool] = None,
    enable_fs: Optional[bool] = None,
) -> List:
    """Build MCP server list for the agent.

    Args:
        context: AgentContext with user-defined tool tasks (may be None).
        working_dir: Working directory to expose via filesystem server.
        enable_shell: Override for shell server (env DFM_AGENT_MCP_SHELL).
        enable_fs:    Override for filesystem server (env DFM_AGENT_MCP_FS).

    Returns:
        List of MCPServerStdio / MCPServerSse instances.
    """
    from agents.mcp import MCPServerStdio, MCPServerSse

    servers = []
    cwd = working_dir or os.getcwd()

    # --- mcp-shell-server -----------------------------------------------
    want_shell = _bool_env("DFM_AGENT_MCP_SHELL", default=True, override=enable_shell)
    if want_shell:
        uvx = shutil.which("uvx")
        if uvx:
            _log.info("Adding mcp-shell-server via uvx")
            servers.append(MCPServerStdio(
                name="shell",
                params={
                    "command": uvx,
                    "args": ["mcp-shell-server"],
                    "env": {"ALLOW_COMMANDS": _SHELL_ALLOW},
                },
            ))
        else:
            _log.debug("uvx not found; skipping mcp-shell-server (coding_tools fallback will be used)")

    # --- @modelcontextprotocol/server-filesystem ------------------------
    want_fs = _bool_env("DFM_AGENT_MCP_FS", default=True, override=enable_fs)
    if want_fs:
        npx = shutil.which("npx")
        if npx:
            _log.info(f"Adding server-filesystem via npx (root: {cwd})")
            servers.append(MCPServerStdio(
                name="filesystem",
                params={
                    "command": npx,
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", cwd],
                },
            ))
        else:
            _log.debug("npx not found; skipping server-filesystem (coding_tools fallback will be used)")

    # --- User-defined MCP servers from AgentTool tasks ------------------
    if context is not None:
        for tool in context.tools:
            cmd = tool.get("command", "")
            url = tool.get("url", "")
            name = tool.get("name", "user-tool")
            args = tool.get("args", [])

            if cmd:
                _log.info(f"Adding user-defined MCP server: {name} ({cmd})")
                servers.append(MCPServerStdio(
                    name=name,
                    params={"command": cmd, "args": args},
                ))
            elif url:
                _log.info(f"Adding user-defined SSE MCP server: {name} ({url})")
                servers.append(MCPServerSse(
                    name=name,
                    params={"url": url},
                ))

    _log.info(f"MCP servers configured: {len(servers)}")
    return servers


def _bool_env(key: str, default: bool, override: Optional[bool]) -> bool:
    if override is not None:
        return override
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip() not in ("0", "false", "no", "")
