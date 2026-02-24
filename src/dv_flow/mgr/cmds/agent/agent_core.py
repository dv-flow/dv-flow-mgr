#****************************************************************************
#* agent_core.py
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
"""DfmAgentCore — wires openai-agents, LiteLLM, DFM tools, and coding tools."""

import asyncio
import logging
import os
from typing import List, Optional, AsyncIterator

_log = logging.getLogger("DfmAgentCore")

# Default model: prefer DFM_MODEL env var, then DFM_PROVIDER prefix, then fallback.
_DEFAULT_MODEL = "github_copilot/gpt-4.1"

# Approval mode constants
APPROVAL_NEVER = "never"   # never ask — run all tools automatically
APPROVAL_AUTO  = "auto"    # ask before write/shell tools
APPROVAL_WRITE = "write"   # alias for auto (kept for CLI compat)

# Tools that require approval in auto/write mode
_WRITE_TOOLS = {"shell_exec", "write_file", "apply_patch"}


def _resolve_model(model_name: Optional[str]) -> str:
    """Determine the LiteLLM model string to use.

    Priority order (highest to lowest):
    1. Explicit ``model_name`` argument (from CLI ``--model`` or config ``model:``)
    2. ``DFM_MODEL`` environment variable
    3. ``DFM_PROVIDER`` environment variable (``<provider>/gpt-4.1``)
    4. Known provider API-key environment variables — first one wins:
       - ``GITHUB_TOKEN``      → ``github_copilot/gpt-4.1``
       - ``OPENAI_API_KEY``    → ``openai/gpt-4.1``
       - ``ANTHROPIC_API_KEY`` → ``anthropic/claude-3-5-sonnet-20241022``
       - ``GEMINI_API_KEY``    → ``gemini/gemini-2.0-flash``
       - ``AZURE_API_KEY``     → ``azure/gpt-4o`` (also needs ``AZURE_API_BASE``)
       - ``OLLAMA_HOST``       → ``ollama/llama3.2``
    5. Default: ``github_copilot/gpt-4.1``
    """
    if model_name:
        return model_name
    if env := os.environ.get("DFM_MODEL"):
        return env
    if provider := os.environ.get("DFM_PROVIDER"):
        return f"{provider}/gpt-4.1"

    # Auto-detect from well-known API-key env vars
    if os.environ.get("GITHUB_TOKEN"):
        return "github_copilot/gpt-4.1"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai/gpt-4.1"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic/claude-3-5-sonnet-20241022"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini/gemini-2.0-flash"
    if os.environ.get("AZURE_API_KEY") and os.environ.get("AZURE_API_BASE"):
        return "azure/gpt-4o"
    if os.environ.get("OLLAMA_HOST"):
        return "ollama/llama3.2"

    return _DEFAULT_MODEL


class DfmAgentCore:
    """Core agent logic: openai-agents Agent + LiteLLM + DFM tools.

    Usage::

        core = DfmAgentCore(context, system_prompt, model_name, pkg, loader)
        # Interactive streaming (for TUI):
        async for event in core.run_streamed(user_message, history):
            ...
        # Single-shot (for Agent task):
        result = await core.run_once(user_message)
    """

    def __init__(
        self,
        context,               # AgentContext (may be None for basic use)
        system_prompt: str,
        model_name: Optional[str] = None,
        pkg=None,
        loader=None,
        builder=None,
        runner=None,
        working_dir: Optional[str] = None,
        approval_mode: str = APPROVAL_AUTO,
        trace: bool = False,
        trace_dir: Optional[str] = None,
        system_prompt_extra: str = "",
        model_settings: Optional[dict] = None,
    ):
        from agents import Agent
        from agents.extensions.models.litellm_model import LitellmModel
        from agents.model_settings import ModelSettings
        from agents.run_config import RunConfig
        from .dfm_tools import build_dfm_tools
        from .coding_tools import build_coding_tools
        from .mcp_setup import build_mcp_servers

        self.context = context
        self.approval_mode = approval_mode if approval_mode in (APPROVAL_NEVER, APPROVAL_AUTO, APPROVAL_WRITE) else APPROVAL_AUTO
        self.model_name = _resolve_model(model_name)
        _log.info(f"Using model: {self.model_name}, approval_mode: {self.approval_mode}")

        # Optional tracing
        if trace:
            self._setup_tracing(trace_dir)

        # Append extra system prompt content
        full_prompt = system_prompt
        if system_prompt_extra:
            full_prompt = system_prompt.rstrip() + "\n\n" + system_prompt_extra.strip()

        # Build LitellmModel — pull well-known keys out of model_settings
        ms = dict(model_settings or {})
        litellm_api_key = ms.pop("api_key", None)
        litellm_base_url = ms.pop("api_base", None)  # api_base → base_url in the constructor

        model = LitellmModel(
            model=self.model_name,
            api_key=litellm_api_key,
            base_url=litellm_base_url,
        )

        # Remaining model_settings entries go into RunConfig.model_settings
        # so they reach every Runner.run() / run_streamed() call automatically.
        custom_headers = ms.pop("headers", None)
        agent_model_settings = ModelSettings(
            extra_headers=custom_headers or None,
            extra_args=ms if ms else None,   # covers ssl_verify, api_version, etc.
        )
        self._run_config = RunConfig(model_settings=agent_model_settings)

        tools = []
        if pkg is not None:
            tools.extend(build_dfm_tools(pkg, loader, builder, runner))
        tools.extend(build_coding_tools())

        # MCP servers (graceful — empty list if nothing available)
        try:
            mcp_servers = build_mcp_servers(context, working_dir=working_dir)
        except Exception as e:
            _log.warning(f"Failed to build MCP servers: {e}; continuing without them")
            mcp_servers = []

        self.agent = Agent(
            name="dfm-assistant",
            instructions=full_prompt,
            model=model,
            tools=tools,
            mcp_servers=mcp_servers,
        )

        # Keep references for hot-reload / introspection
        self.pkg = pkg
        self.loader = loader

    def _setup_tracing(self, trace_dir: Optional[str]):
        """Enable openai-agents file tracing."""
        import datetime
        try:
            from agents.tracing import set_trace_processors
            from agents.tracing.processors import FileSpanExporter, BatchTraceProcessor
            tdir = trace_dir or os.path.expanduser("~/.dfm/traces")
            os.makedirs(tdir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            trace_file = os.path.join(tdir, f"trace_{ts}.jsonl")
            exporter = FileSpanExporter(trace_file)
            set_trace_processors([BatchTraceProcessor(exporter)])
            _log.info(f"Tracing enabled: {trace_file}")
        except Exception as e:
            _log.warning(f"Could not enable tracing: {e}")

    async def _connect_mcp(self):
        """Connect all MCP servers; return an AsyncExitStack to clean up with."""
        import contextlib
        stack = contextlib.AsyncExitStack()
        await stack.__aenter__()
        for server in self.agent.mcp_servers:
            try:
                await stack.enter_async_context(server)
            except Exception as e:
                _log.warning(f"Could not connect MCP server {getattr(server, 'name', server)}: {e}")
        return stack

    async def run_streamed(self, user_message: str, history: Optional[List] = None) -> AsyncIterator:
        """Stream a response; yields openai-agents StreamEvent objects."""
        from agents import Runner
        input_messages = list(history or []) + [{"role": "user", "content": user_message}]
        stack = await self._connect_mcp()
        try:
            result = Runner.run_streamed(self.agent, input_messages, run_config=self._run_config)
            async for event in result.stream_events():
                yield event
        finally:
            await stack.__aexit__(None, None, None)

    async def run_once(self, user_message: str, history: Optional[List] = None,
                       max_retries: int = 3, retry_delay: float = 2.0):
        """Non-streaming single-shot run with retry on transient errors."""
        from agents import Runner
        input_messages = list(history or []) + [{"role": "user", "content": user_message}]

        async with await self._connect_mcp():
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await Runner.run(self.agent, input_messages, run_config=self._run_config)
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    if any(kw in msg for kw in ("rate limit", "timeout", "connection", "503", "429", "502")):
                        if attempt < max_retries:
                            delay = retry_delay * (2 ** attempt)
                            _log.warning(f"Transient error (attempt {attempt+1}/{max_retries+1}): {exc}. Retrying in {delay:.1f}s…")
                            await asyncio.sleep(delay)
                            continue
                    raise
            raise last_exc
