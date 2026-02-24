"""Tests for agent config loader — env-var expansion and model_settings."""
import os
import textwrap
import pytest
from pathlib import Path


class TestEnvExpansion:

    def test_expand_simple_string(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        from dv_flow.mgr.cmds.agent.config import _expand_env
        assert _expand_env("${{ env.MY_KEY }}") == "secret123"

    def test_expand_embedded(self, monkeypatch):
        monkeypatch.setenv("HOST", "api.example.com")
        from dv_flow.mgr.cmds.agent.config import _expand_env
        assert _expand_env("https://${{ env.HOST }}/v1") == "https://api.example.com/v1"

    def test_expand_dict(self, monkeypatch):
        monkeypatch.setenv("AUTH_TOKEN", "abc-def")
        from dv_flow.mgr.cmds.agent.config import _expand_env
        result = _expand_env({"X-Auth-Token": "${{ env.AUTH_TOKEN }}"})
        assert result == {"X-Auth-Token": "abc-def"}

    def test_expand_nested(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "tok")
        from dv_flow.mgr.cmds.agent.config import _expand_env
        result = _expand_env({"headers": {"X-Auth": "${{ env.TOKEN }}"}})
        assert result == {"headers": {"X-Auth": "tok"}}

    def test_expand_list(self, monkeypatch):
        monkeypatch.setenv("VAL", "hello")
        from dv_flow.mgr.cmds.agent.config import _expand_env
        assert _expand_env(["${{ env.VAL }}", "static"]) == ["hello", "static"]

    def test_missing_env_var_returns_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_XYZ", raising=False)
        from dv_flow.mgr.cmds.agent.config import _expand_env
        assert _expand_env("${{ env.NONEXISTENT_XYZ }}") == ""

    def test_non_string_passthrough(self):
        from dv_flow.mgr.cmds.agent.config import _expand_env
        assert _expand_env(42) == 42
        assert _expand_env(False) is False
        assert _expand_env(None) is None


class TestConfigFileLoading:

    def test_load_model_settings_from_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_AUTH_TOKEN", "subkey999")
        cfg_file = tmp_path / ".dfm" / "agent.yaml"
        cfg_file.parent.mkdir()
        cfg_file.write_text(textwrap.dedent("""\
            model: openai/gpt-4o
            model_settings:
              api_base: https://llm-proxy.example.com
              api_key: "${{ env.MY_AUTH_TOKEN }}"
              api_version: "2024-06-01"
              ssl_verify: false
              headers:
                X-Auth-Token: "${{ env.MY_AUTH_TOKEN }}"
        """))

        from dv_flow.mgr.cmds.agent.config import load_config
        cfg = load_config(cwd=str(tmp_path))

        assert cfg.model == "openai/gpt-4o"
        ms = cfg.model_settings
        assert ms["api_base"] == "https://llm-proxy.example.com"
        assert ms["api_key"] == "subkey999"
        assert ms["api_version"] == "2024-06-01"
        assert ms["ssl_verify"] is False
        assert ms["headers"]["X-Auth-Token"] == "subkey999"

    def test_empty_model_settings_default(self, tmp_path):
        cfg_file = tmp_path / ".dfm" / "agent.yaml"
        cfg_file.parent.mkdir()
        cfg_file.write_text("model: openai/gpt-4o\n")

        from dv_flow.mgr.cmds.agent.config import load_config
        cfg = load_config(cwd=str(tmp_path))
        assert cfg.model_settings == {}

    def test_model_settings_preserved_in_apply_cli(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTH_KEY", "xyz")
        cfg_file = tmp_path / ".dfm" / "agent.yaml"
        cfg_file.parent.mkdir()
        cfg_file.write_text(textwrap.dedent("""\
            model_settings:
              headers:
                X-Auth: "${{ env.AUTH_KEY }}"
        """))

        from dv_flow.mgr.cmds.agent.config import load_config

        class FakeArgs:
            model = None
            approval_mode = None
            trace = False

        cfg = load_config(cwd=str(tmp_path)).apply_cli(FakeArgs())
        assert cfg.model_settings["headers"]["X-Auth"] == "xyz"


class TestResolveModel:
    """Tests for _resolve_model() auto-detection from env vars."""

    def _clear_env(self, monkeypatch):
        for var in ("DFM_MODEL", "DFM_PROVIDER", "GITHUB_TOKEN", "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_API_KEY",
                    "AZURE_API_BASE", "OLLAMA_HOST"):
            monkeypatch.delenv(var, raising=False)

    def test_explicit_model_wins(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model("openai/gpt-4o") == "openai/gpt-4o"

    def test_dfm_model_env(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("DFM_MODEL", "ollama/codestral")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "ollama/codestral"

    def test_github_token_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "github_copilot/gpt-4.1"

    def test_openai_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "openai/gpt-4.1"

    def test_anthropic_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "anthropic/claude-3-5-sonnet-20241022"

    def test_gemini_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "gemini/gemini-2.0-flash"

    def test_azure_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("AZURE_API_KEY", "azure-key")
        monkeypatch.setenv("AZURE_API_BASE", "https://my.openai.azure.com")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "azure/gpt-4o"

    def test_azure_requires_both_vars(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("AZURE_API_KEY", "azure-key")
        # AZURE_API_BASE not set — should not auto-detect azure
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "github_copilot/gpt-4.1"  # fallback

    def test_ollama_auto_detect(self, monkeypatch):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "ollama/llama3.2"

    def test_default_fallback(self, monkeypatch):
        self._clear_env(monkeypatch)
        from dv_flow.mgr.cmds.agent.agent_core import _resolve_model
        assert _resolve_model(None) == "github_copilot/gpt-4.1"
