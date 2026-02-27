#****************************************************************************
#* config.py
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
"""Agent configuration loader.

Loads ~/.dfm/agent.yaml and .dfm/agent.yaml (project-local, wins over user).
CLI flags always win over config-file values.

Schema example::

    model: azure/my-deployment
    approval_mode: auto          # never | auto | write
    trace: false
    system_prompt_extra: |
        Always prefer minimal diffs.

    # LiteLLM model-level settings (all optional)
    model_settings:
      api_base:    https://llm-api.example.com
      api_key:     dummy          # or "${{ env.MY_API_KEY }}"
      api_version: "2024-06-01"
      ssl_verify:  false
      headers:
        X-Auth-Token: "${{ env.LLM_AUTH_TOKEN }}"
        X-Custom-Header: some-value

    mcp_servers:
      - name: my-tool
        command: uvx
        args: [mcp-my-tool]

Environment variable references use ``${{ env.VAR_NAME }}`` syntax anywhere
a string value appears (model name, headers, api_key, etc.).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("AgentConfig")

_USER_CONFIG = os.path.expanduser("~/.dfm/agent.yaml")
_LOCAL_CONFIG = os.path.join(".dfm", "agent.yaml")


@dataclass
class AgentConfig:
    """Resolved agent configuration (config files merged, CLI flags not yet applied)."""

    model: Optional[str] = None
    approval_mode: str = "auto"       # never | auto | write
    trace: bool = False
    trace_dir: Optional[str] = None   # None → ~/.dfm/traces/
    system_prompt_extra: str = ""
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)
    # LiteLLM model-level settings passed through to the completion call
    model_settings: Dict[str, Any] = field(default_factory=dict)

    def apply_cli(self, args) -> "AgentConfig":
        """Return a new AgentConfig with CLI flag values overlaid (flags win)."""
        c = AgentConfig(
            model=self.model,
            approval_mode=self.approval_mode,
            trace=self.trace,
            trace_dir=self.trace_dir,
            system_prompt_extra=self.system_prompt_extra,
            mcp_servers=list(self.mcp_servers),
            model_settings=dict(self.model_settings),
        )
        if getattr(args, 'model', None):
            c.model = args.model
        if getattr(args, 'approval_mode', None):
            c.approval_mode = args.approval_mode
        if getattr(args, 'trace', False):
            c.trace = True
        return c


def load_config(cwd: Optional[str] = None) -> AgentConfig:
    """Load and merge user + project config files. Returns AgentConfig."""
    cfg: Dict[str, Any] = {}

    # User config (lower priority)
    _merge_yaml(cfg, _USER_CONFIG)

    # Project-local config (higher priority)
    local = os.path.join(cwd or os.getcwd(), _LOCAL_CONFIG)
    _merge_yaml(cfg, local)

    return _dict_to_config(cfg)


def _merge_yaml(target: Dict, path: str):
    if not os.path.exists(path):
        return
    try:
        import yaml
        with open(path) as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            target.update(data)
    except Exception as e:
        _log.warning(f"Could not load agent config {path}: {e}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${{ env.VAR }}`` references in strings/dicts/lists."""
    if isinstance(value, str):
        def _replace(m):
            var = m.group(1).strip()
            result = os.environ.get(var)
            if result is None:
                _log.warning(f"Config references undefined env var: {var}")
                return ""
            return result
        return re.sub(r'\$\{\{\s*env\.([^}]+?)\s*\}\}', _replace, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _dict_to_config(d: Dict) -> AgentConfig:
    raw_ms = d.get("model_settings", {}) or {}
    expanded_ms = _expand_env(raw_ms)
    return AgentConfig(
        model=_expand_env(d.get("model")),
        approval_mode=d.get("approval_mode", "auto"),
        trace=bool(d.get("trace", False)),
        trace_dir=d.get("trace_dir"),
        system_prompt_extra=d.get("system_prompt_extra", ""),
        mcp_servers=list(d.get("mcp_servers", [])),
        model_settings=expanded_ms if isinstance(expanded_ms, dict) else {},
    )
