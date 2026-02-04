"""
Unit tests for assistant_launcher.py

Tests command building for different AI assistants.
"""
import pytest
from unittest.mock import MagicMock

from dv_flow.mgr.cmds.agent.assistant_launcher import AssistantLauncher
from dv_flow.mgr.cmds.agent.context_builder import AgentContext


class TestAssistantLauncher:
    """Tests for AssistantLauncher class."""
    
    def test_init_with_defaults(self):
        """Test launcher initialization with defaults."""
        launcher = AssistantLauncher()
        assert launcher.assistant_name is None
        assert launcher.model is None
    
    def test_init_with_assistant_name(self):
        """Test launcher initialization with assistant name."""
        launcher = AssistantLauncher(assistant_name="codex")
        assert launcher.assistant_name == "codex"
        assert launcher.model is None
    
    def test_init_with_model(self):
        """Test launcher initialization with model."""
        launcher = AssistantLauncher(assistant_name="codex", model="gpt-4")
        assert launcher.assistant_name == "codex"
        assert launcher.model == "gpt-4"


class TestBuildCopilotCommand:
    """Tests for _build_copilot_command method."""
    
    def test_basic_command(self, tmp_path):
        """Test basic copilot command generation."""
        launcher = AssistantLauncher(assistant_name="copilot")
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        cmd = launcher._build_copilot_command(context_file, working_dir, context)
        
        assert cmd[0] == "copilot"
        assert "-i" in cmd
        assert "--allow-all-tools" in cmd
        assert "--add-dir" in cmd
        assert working_dir in cmd
    
    def test_with_model(self, tmp_path):
        """Test copilot command with model specified."""
        launcher = AssistantLauncher(assistant_name="copilot", model="gpt-4o")
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        cmd = launcher._build_copilot_command(context_file, working_dir, context)
        
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "gpt-4o"


class TestBuildCodexCommand:
    """Tests for _build_codex_command method."""
    
    def test_basic_command(self, tmp_path):
        """Test basic codex command generation."""
        launcher = AssistantLauncher(assistant_name="codex")
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        cmd = launcher._build_codex_command(context_file, working_dir, context)
        
        assert cmd[0] == "codex"
        # Should have sandbox mode
        assert "-s" in cmd
        sandbox_idx = cmd.index("-s")
        assert cmd[sandbox_idx + 1] == "workspace-write"
        # Should have prompt as last argument
        assert "context" in cmd[-1].lower()
    
    def test_with_model(self, tmp_path):
        """Test codex command with model specified."""
        launcher = AssistantLauncher(assistant_name="codex", model="o3")
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        cmd = launcher._build_codex_command(context_file, working_dir, context)
        
        assert "-m" in cmd
        model_idx = cmd.index("-m")
        assert cmd[model_idx + 1] == "o3"
    
    def test_no_invalid_flags(self, tmp_path):
        """Test that codex command doesn't have invalid flags."""
        launcher = AssistantLauncher(assistant_name="codex")
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        cmd = launcher._build_codex_command(context_file, working_dir, context)
        
        # These flags don't exist in codex CLI
        assert "--writable-root" not in cmd
        assert "-q" not in cmd
        assert "--approval-mode" not in cmd
        assert "--sandbox" not in cmd  # Should use -s not --sandbox


class TestCommandBuilderParameterized:
    """Parameterized tests across assistants."""
    
    @pytest.mark.parametrize("assistant_name,expected_binary", [
        ("copilot", "copilot"),
        ("codex", "codex"),
    ])
    def test_command_starts_with_binary(self, assistant_name, expected_binary, tmp_path):
        """Test that commands start with correct binary name."""
        launcher = AssistantLauncher(assistant_name=assistant_name)
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        if assistant_name == "copilot":
            cmd = launcher._build_copilot_command(context_file, working_dir, context)
        else:
            cmd = launcher._build_codex_command(context_file, working_dir, context)
        
        assert cmd[0] == expected_binary
    
    @pytest.mark.parametrize("assistant_name", ["copilot", "codex"])
    def test_command_is_list_of_strings(self, assistant_name, tmp_path):
        """Test that command is a list of strings."""
        launcher = AssistantLauncher(assistant_name=assistant_name)
        context = AgentContext()
        context_file = str(tmp_path / "context.md")
        working_dir = str(tmp_path)
        
        if assistant_name == "copilot":
            cmd = launcher._build_copilot_command(context_file, working_dir, context)
        else:
            cmd = launcher._build_codex_command(context_file, working_dir, context)
        
        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)
        assert len(cmd) > 1  # At least binary + some args
