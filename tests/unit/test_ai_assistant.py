import pytest
import asyncio
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


@pytest.mark.asyncio
async def test_openai_not_implemented():
    """Test that OpenAI execute raises NotImplementedError"""
    assistant = OpenAIAssistant()
    
    with pytest.raises(NotImplementedError):
        await assistant.execute("test prompt", "/tmp", "", {})


@pytest.mark.asyncio
async def test_claude_not_implemented():
    """Test that Claude execute raises NotImplementedError"""
    assistant = ClaudeAssistant()
    
    with pytest.raises(NotImplementedError):
        await assistant.execute("test prompt", "/tmp", "", {})


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
