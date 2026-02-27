#****************************************************************************
#* repl.py
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
"""Basic REPL for the native DFM agent (Phase 1 — no fancy TUI yet).

Provides a readline-style interactive loop backed by prompt_toolkit with
history persistence. Replace with tui.py in Phase 2.
"""

import asyncio
import logging
import os
import sys
from typing import List, Dict

_log = logging.getLogger("DfmRepl")

_HISTORY_FILE = os.path.expanduser("~/.dfm/agent_history")

_SLASH_HELP = """\
Slash commands:
  /clear      Clear conversation history
  /model      Show current model
  /tools      List available tools
  /skills     List skills/personas discovered in the project
  /exit       Quit (also Ctrl+D)
  /help       Show this help
"""


class DfmRepl:
    """Interactive REPL backed by prompt_toolkit."""

    def __init__(self, agent_core, pkg=None):
        """
        Args:
            agent_core: DfmAgentCore instance.
            pkg: Root package (for /skills command).
        """
        self.agent = agent_core
        self.pkg = pkg or getattr(agent_core, 'pkg', None)
        self.history: List[Dict] = []

    async def run(self) -> int:
        """Run the REPL until the user exits. Returns exit code."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory

        os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
        session = PromptSession(history=FileHistory(_HISTORY_FILE))

        self._print_banner()

        while True:
            try:
                user_input = await session.prompt_async("> ")
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n(Use /exit or Ctrl+D to quit)")
                continue

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                if await self._handle_command(user_input):
                    break
                continue

            self.history.append({"role": "user", "content": user_input})
            await self._get_response(user_input)

        return 0

    # ------------------------------------------------------------------ #

    def _print_banner(self):
        model = getattr(self.agent, 'model_name', 'unknown')
        pkg_name = getattr(self.pkg, 'name', '') if self.pkg else ''
        print(f"\nDFM Agent  |  model: {model}  |  project: {pkg_name}")
        print("Type /help for commands, Ctrl+D to exit.\n")

    async def _get_response(self, user_input: str):
        """Run agent and print the response."""
        from agents.stream_events import RawResponsesStreamEvent
        try:
            accumulated = ""
            async for event in self.agent.run_streamed(user_input, self.history[:-1]):
                if isinstance(event, RawResponsesStreamEvent):
                    for part in getattr(event.data, 'delta', []):
                        text = getattr(part, 'text', None) or getattr(part, 'delta', None) or ""
                        if text:
                            print(text, end="", flush=True)
                            accumulated += text
            print()  # newline after streaming
            if accumulated:
                self.history.append({"role": "assistant", "content": accumulated})
        except KeyboardInterrupt:
            print("\n[cancelled]")
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)
            _log.debug("Agent error", exc_info=True)

    async def _handle_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if user wants to exit."""
        parts = cmd.split()
        name = parts[0].lower()

        if name in ("/exit", "/quit"):
            return True
        elif name == "/clear":
            self.history.clear()
            print("Conversation cleared.")
        elif name == "/model":
            print(f"Model: {getattr(self.agent, 'model_name', 'unknown')}")
        elif name == "/tools":
            tools = getattr(self.agent.agent, 'tools', [])
            if tools:
                print("Available tools:")
                for t in tools:
                    name_ = getattr(t, 'name', str(t))
                    desc = (getattr(t, 'description', '') or '').split('\n')[0]
                    print(f"  {name_}  {desc}")
            else:
                print("No tools registered.")
        elif name == "/skills":
            await self._show_skills()
        elif name == "/help":
            print(_SLASH_HELP)
        else:
            print(f"Unknown command: {parts[0]}. Type /help for available commands.")

        return False

    async def _show_skills(self):
        """Print skills and personas discovered in the project."""
        if self.pkg is None:
            print("No project loaded.")
            return
        skills, personas = [], []
        for task in self.pkg.task_m.values():
            uses = getattr(task, 'uses', None)
            if uses is None:
                continue
            tags = getattr(uses, 'tags', []) or []
            tag_names = {t.name if hasattr(t, 'name') else str(t) for t in tags}
            entry = f"  {task.name}" + (f"  — {task.desc}" if task.desc else "")
            if 'std.AgentSkillTag' in tag_names:
                skills.append(entry)
            if 'std.AgentPersonaTag' in tag_names:
                personas.append(entry)

        if skills:
            print("Skills:")
            for s in skills:
                print(s)
        else:
            print("Skills: (none found)")

        if personas:
            print("Personas:")
            for p in personas:
                print(p)
        else:
            print("Personas: (none found)")
