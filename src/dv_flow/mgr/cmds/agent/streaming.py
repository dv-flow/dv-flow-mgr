#****************************************************************************
#* streaming.py
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
"""Streaming event translator.

Translates raw openai-agents StreamEvents into simplified DfmStreamEvent
dataclasses that the TUI (and any other consumer) can handle without
importing openai internals directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional


# ---------------------------------------------------------------------------
# Simplified event types emitted by the translator
# ---------------------------------------------------------------------------

@dataclass
class TextDelta:
    """A chunk of response text from the LLM."""
    delta: str
    type: str = "text_delta"


@dataclass
class ToolCallStart:
    """The agent is about to call a tool."""
    tool_name: str
    args: str          # JSON-encoded arguments string
    call_id: str = ""
    type: str = "tool_call_start"


@dataclass
class ToolCallResult:
    """The tool returned a result."""
    tool_name: str
    result: str        # String result (may be JSON)
    call_id: str = ""
    type: str = "tool_call_result"


@dataclass
class MessageComplete:
    """A full assistant message is finalised."""
    content: str
    type: str = "message_complete"


@dataclass
class AgentHandoff:
    """The agent handed off to another agent."""
    from_agent: str
    to_agent: str
    type: str = "agent_handoff"


@dataclass
class UsageSummary:
    """Token usage for the completed turn."""
    input_tokens: int = 0
    output_tokens: int = 0
    type: str = "usage_summary"


DfmStreamEvent = TextDelta | ToolCallStart | ToolCallResult | MessageComplete | AgentHandoff | UsageSummary


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------

async def translate_stream(raw_stream) -> AsyncIterator[DfmStreamEvent]:
    """Yield simplified DfmStreamEvent objects from a raw openai-agents stream.

    Args:
        raw_stream: AsyncIterator of openai-agents StreamEvent objects
                    (returned by Runner.run_streamed().stream_events()).

    Yields:
        DfmStreamEvent instances.
    """
    from openai.types.responses import ResponseTextDeltaEvent
    from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent, AgentUpdatedStreamEvent
    from agents.items import ToolCallItem, ToolCallOutputItem, MessageOutputItem, ItemHelpers

    # Track tool name by call id for result correlation
    _pending_calls: dict[str, str] = {}

    async for event in raw_stream:
        # ---- text deltas -----------------------------------------------
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if isinstance(data, ResponseTextDeltaEvent):
                yield TextDelta(delta=data.delta)

        # ---- tool calls / outputs / messages ---------------------------
        elif isinstance(event, RunItemStreamEvent):
            item = event.item
            name = event.name

            if name == "tool_called" and isinstance(item, ToolCallItem):
                raw = item.raw_item
                # Extract tool name and arguments from the raw function call item
                tool_name = _get_attr(raw, 'name') or _get_attr(raw, 'function', 'name') or "unknown_tool"
                raw_args = _get_attr(raw, 'arguments') or _get_attr(raw, 'function', 'arguments') or "{}"
                call_id = _get_attr(raw, 'call_id') or _get_attr(raw, 'id') or ""
                _pending_calls[call_id] = tool_name
                yield ToolCallStart(tool_name=tool_name, args=raw_args, call_id=call_id)

            elif name == "tool_output" and isinstance(item, ToolCallOutputItem):
                raw = item.raw_item
                call_id = _get_attr(raw, 'call_id') or ""
                tool_name = _pending_calls.pop(call_id, "unknown_tool")
                output_str = str(item.output) if item.output is not None else ""
                yield ToolCallResult(tool_name=tool_name, result=output_str, call_id=call_id)

            elif name == "message_output_created" and isinstance(item, MessageOutputItem):
                content = ItemHelpers.extract_last_text(item.raw_item) or ""
                if content:
                    yield MessageComplete(content=content)

            elif name in ("handoff_requested", "handoff_occured"):
                from_agent = getattr(getattr(item, 'agent', None), 'name', '') or ""
                to_agent = _get_attr(item.raw_item, 'agent_name') or ""
                yield AgentHandoff(from_agent=from_agent, to_agent=to_agent)

        # ---- usage (attached to AgentUpdatedStreamEvent on last turn) --
        elif isinstance(event, AgentUpdatedStreamEvent):
            pass  # usage lives on RunResult, emitted by caller after stream ends


def _get_attr(obj, *keys):
    """Walk a chain of attribute/dict keys, return first truthy value found."""
    current = obj
    for key in keys:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return current
