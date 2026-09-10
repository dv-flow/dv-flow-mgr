"""Live integration test for the native agent.

Uses the GitHub Models API with the automatically-available GITHUB_TOKEN.
Skipped when GITHUB_TOKEN is absent.

Run explicitly in CI via the `agent-integration` workflow, or locally:

    GITHUB_TOKEN=$(gh auth token) pytest tests/unit/test_native_agent_live.py -v

PROVIDER STATUS -- read before treating a skip here as coverage.

GitHub Models is being retired, so this test currently SKIPS rather than runs.
The original base URL, https://models.inference.ai.azure.com, stopped resolving
in DNS entirely (NXDOMAIN); litellm surfaced that as a bare "OpenAIException -
Connection error", which is why the failure read like a transient outage and
burned three retries before failing CI on every push from 2026-08-31 onward.
The successor host below is not a fix -- it answers, but with HTTP 410
`github_models_retirement_brownout`. It is used because a host that returns a
diagnosable status beats one that does not resolve.

The consequence is that a green `agent-integration` run now proves nothing
about the agent talking to a real model; the skip reason is the only place the
distinction shows up. Restoring real coverage means pointing this at a provider
that is not being decommissioned (`github_copilot` via the org COPILOT_TOKEN,
or a paid OPENAI_API_KEY/ANTHROPIC_API_KEY secret) and dropping the
unavailability skip below so an outage fails loudly again.
"""
import asyncio
import importlib.util
import os
import pytest

# Disable MCP servers for this test — they require external tools (uvx/npx)
# that may not be installed, and aren't needed for a basic connectivity test.
os.environ.setdefault("DFM_AGENT_MCP_SHELL", "0")
os.environ.setdefault("DFM_AGENT_MCP_FS", "0")

# Skip the whole module when no provider credentials are available,
# or when the optional 'agents' package is not installed.
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="GITHUB_TOKEN not set — skipping live agent integration test",
    ),
    pytest.mark.skipif(
        importlib.util.find_spec("agents") is None,
        reason="'agents' package not installed — skipping live agent integration test",
    ),
]

# GitHub Models. Requires GITHUB_TOKEN with `models: read` (auto-granted in
# Actions). See PROVIDER STATUS above: this endpoint is in retirement brownout,
# so in practice the request below fails and the test skips.
_GITHUB_MODELS_BASE = "https://models.github.ai/inference"
_TEST_MODEL = os.environ.get("AGENT_TEST_MODEL", "openai/gpt-4o-mini")

# Substrings marking "the provider is gone or unreachable", as opposed to a
# genuine agent bug. Matched against the stringified exception, because litellm
# flattens transport and HTTP failures into a handful of generic exception types
# whose class alone does not distinguish the two. `410`/`retirement` catch the
# brownout; the rest catch DNS/TCP/TLS failures and gateway errors.
_UNAVAILABLE_MARKERS = (
    "410",
    "retirement",
    "connection error",
    "apiconnectionerror",
    "could not resolve",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "connection refused",
    "connection reset",
    "502",
    "503",
    "504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
)


def _is_provider_unavailable(exc: BaseException) -> bool:
    """True when `exc` looks like provider unavailability rather than a defect.

    Walks the __cause__/__context__ chain: litellm commonly re-raises a wrapped
    error whose own message is generic while the underlying socket error carries
    the specific text we key on.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        text = f"{type(exc).__name__}: {exc}".lower()
        if any(marker in text for marker in _UNAVAILABLE_MARKERS):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


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
        try:
            result = await core.run_once(
                "Reply with exactly one word: PONG",
                max_retries=2,
            )
        except Exception as exc:
            if _is_provider_unavailable(exc):
                pytest.skip(
                    f"Model provider unavailable at {_GITHUB_MODELS_BASE} "
                    f"({type(exc).__name__}: {exc}) — see PROVIDER STATUS in this "
                    f"module. The agent was NOT exercised."
                )
            raise

        assert result is not None, "run_once returned None"
        text = getattr(result, "final_output", None) or str(result)
        assert text.strip(), "Model returned an empty response"
        assert "PONG" in text.upper(), f"Expected PONG in response, got: {text!r}"

    asyncio.run(_impl())
