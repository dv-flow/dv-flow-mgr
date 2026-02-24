"""Live integration test for the native agent.

Uses the GitHub Models API (https://models.inference.ai.azure.com) with the
automatically-available GITHUB_TOKEN.  Skipped when GITHUB_TOKEN is absent.

Run explicitly in CI via the `agent-integration` workflow, or locally:

    GITHUB_TOKEN=$(gh auth token) pytest tests/unit/test_native_agent_live.py -v
"""
import asyncio
import os
import pytest

# Disable MCP servers for this test — they require external tools (uvx/npx)
# that may not be installed, and aren't needed for a basic connectivity test.
os.environ.setdefault("DFM_AGENT_MCP_SHELL", "0")
os.environ.setdefault("DFM_AGENT_MCP_FS", "0")

# Skip the whole module when no provider credentials are available.
pytestmark = pytest.mark.skipif(
    not os.environ.get("GITHUB_TOKEN"),
    reason="GITHUB_TOKEN not set — skipping live agent integration test",
)

# Use GitHub Models (free, 0 premium requests, no Copilot subscription needed).
# Requires GITHUB_TOKEN with `models: read` permission (auto-granted in Actions).
_GITHUB_MODELS_BASE = "https://models.inference.ai.azure.com"
_TEST_MODEL = os.environ.get("AGENT_TEST_MODEL", "openai/gpt-4o-mini")


def test_native_agent_responds():
    """Native agent sends a prompt and receives a non-empty reply."""
    async def _impl():
        from dv_flow.mgr.cmds.agent.agent_core import DfmAgentCore

        core = DfmAgentCore(
            context=None,
            system_prompt="You are a helpful assistant. Be concise.",
            model_name=_TEST_MODEL,
            approval_mode="never",
            model_settings={
                "api_base": _GITHUB_MODELS_BASE,
                "api_key": os.environ["GITHUB_TOKEN"],
            },
        )
        result = await core.run_once(
            "Reply with exactly one word: PONG",
            max_retries=2,
        )
        assert result is not None, "run_once returned None"
        text = getattr(result, "final_output", None) or str(result)
        assert text.strip(), "Model returned an empty response"
        assert "PONG" in text.upper(), f"Expected PONG in response, got: {text!r}"

    asyncio.run(_impl())
