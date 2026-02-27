import pytest
import asyncio
import inspect
from dv_flow.mgr.std.ai_assistant import (
    get_assistant,
    CopilotAssistant,
    CodexAssistant,
    OpenAIAssistant,
    ClaudeAssistant,
    ASSISTANT_REGISTRY,
    ASSISTANT_PRIORITY,
    probe_available_assistant,
    get_available_assistant_name
)


def test_assistant_registry():
    """Test that all expected assistants are registered"""
    assert "copilot" in ASSISTANT_REGISTRY
    assert "codex" in ASSISTANT_REGISTRY
    assert "openai" in ASSISTANT_REGISTRY
    assert "claude" in ASSISTANT_REGISTRY


def test_assistant_priority():
    """Test that priority order is defined correctly"""
    assert "copilot" in ASSISTANT_PRIORITY
    assert "codex" in ASSISTANT_PRIORITY
    # copilot should be first priority
    assert ASSISTANT_PRIORITY.index("copilot") < ASSISTANT_PRIORITY.index("codex")


def test_get_assistant_valid():
    """Test getting a valid assistant"""
    assistant = get_assistant("copilot")
    assert isinstance(assistant, CopilotAssistant)
    
    assistant = get_assistant("codex")
    assert isinstance(assistant, CodexAssistant)
    
    assistant = get_assistant("openai")
    assert isinstance(assistant, OpenAIAssistant)
    
    assistant = get_assistant("claude")
    assert isinstance(assistant, ClaudeAssistant)


def test_get_assistant_invalid():
    """Test getting an invalid assistant raises ValueError"""
    with pytest.raises(ValueError) as exc_info:
        get_assistant("nonexistent")
    
    assert "Unknown AI assistant" in str(exc_info.value)
    assert "nonexistent" in str(exc_info.value)


def test_copilot_check_available():
    """Test copilot availability check"""
    assistant = CopilotAssistant()
    is_available, error_msg = assistant.check_available()
    
    # Result depends on environment, but should return bool and string
    assert isinstance(is_available, bool)
    assert isinstance(error_msg, str)
    
    if not is_available:
        # Error message should be helpful
        assert len(error_msg) > 0
        assert "gh" in error_msg.lower() or "copilot" in error_msg.lower()


def test_codex_check_available():
    """Test codex availability check"""
    assistant = CodexAssistant()
    is_available, error_msg = assistant.check_available()
    
    # Result depends on environment, but should return bool and string
    assert isinstance(is_available, bool)
    assert isinstance(error_msg, str)
    
    if not is_available:
        # Error message should be helpful
        assert len(error_msg) > 0
        assert "codex" in error_msg.lower()


def test_openai_check_available():
    """Test OpenAI availability check"""
    assistant = OpenAIAssistant()
    is_available, error_msg = assistant.check_available()
    
    assert isinstance(is_available, bool)
    assert isinstance(error_msg, str)


def test_claude_check_available():
    """Test Claude availability check"""
    assistant = ClaudeAssistant()
    is_available, error_msg = assistant.check_available()
    
    assert isinstance(is_available, bool)
    assert isinstance(error_msg, str)


def test_openai_not_implemented():
    async def _impl():
        """Test that OpenAI execute raises NotImplementedError"""
        assistant = OpenAIAssistant()
        
        with pytest.raises(NotImplementedError):
            await assistant.execute("test prompt", "/tmp", "", {})
    asyncio.run(_impl())

def test_claude_not_implemented():
    async def _impl():
        """Test that Claude execute raises NotImplementedError"""
        assistant = ClaudeAssistant()
        
        with pytest.raises(NotImplementedError):
            await assistant.execute("test prompt", "/tmp", "", {})
    asyncio.run(_impl())

def test_probe_available_assistant():
    """Test auto-probe for available assistant"""
    # This test validates the probe logic without requiring specific CLI
    result = probe_available_assistant()
    
    # Result should be either an assistant instance or None
    if result is not None:
        assert hasattr(result, 'execute')
        assert hasattr(result, 'check_available')


def test_get_available_assistant_name():
    """Test getting available assistant name"""
    result = get_available_assistant_name()
    
    # Result should be either a string name or None
    if result is not None:
        assert isinstance(result, str)
        assert result in ASSISTANT_REGISTRY


# ============================================================================
# Parameterized tests across all supported assistants
# ============================================================================

@pytest.mark.parametrize("assistant_name", ["copilot", "codex"])
def test_assistant_check_available_returns_tuple(assistant_name):
    """Test that check_available returns proper tuple for priority assistants."""
    assistant = get_assistant(assistant_name)
    result = assistant.check_available()
    
    assert isinstance(result, tuple), f"{assistant_name}: should return tuple"
    assert len(result) == 2, f"{assistant_name}: tuple should have 2 elements"
    assert isinstance(result[0], bool), f"{assistant_name}: first element should be bool"
    assert isinstance(result[1], str), f"{assistant_name}: second element should be str"


@pytest.mark.parametrize("assistant_name", ["copilot", "codex"])
def test_assistant_has_execute_method(assistant_name):
    """Test that priority assistants have async execute method."""
    assistant = get_assistant(assistant_name)
    
    assert hasattr(assistant, 'execute'), f"{assistant_name}: should have execute method"
    assert inspect.iscoroutinefunction(assistant.execute), f"{assistant_name}: execute should be async"


@pytest.mark.parametrize("assistant_name", ["copilot", "codex"])
def test_assistant_has_name_classmethod(assistant_name):
    """Test that priority assistants have name classmethod."""
    assistant_cls = ASSISTANT_REGISTRY[assistant_name]
    
    assert hasattr(assistant_cls, 'name'), f"{assistant_name}: should have name classmethod"
    assert assistant_cls.name() == assistant_name, f"{assistant_name}: name() should return '{assistant_name}'"


def test_available_assistant_fixture(available_assistant):
    """Test that the available_assistant fixture works correctly.
    
    This test uses the parameterized fixture from conftest.py.
    It will skip if the assistant is not available.
    """
    name, assistant = available_assistant
    
    # If we get here, the assistant is available
    is_available, error = assistant.check_available()
    assert is_available is True
    assert error == ""
    assert name in ASSISTANT_PRIORITY
