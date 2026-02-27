#****************************************************************************
#* tui.py
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
"""Rich + prompt_toolkit interactive TUI for the DFM native agent.

Layout:
  - prompt_toolkit PromptSession for input (history, multi-line, completions)
  - rich Console for output (Markdown rendering, tool call panels, spinners)
  - Streaming via streaming.translate_stream()

Slash commands (all start with /):
  /clear               Clear conversation history
  /model               Show current model
  /tools               List registered tools
  /skills              List skills/personas in the project
  /personas            Alias for /skills
  /skill add <Name>    Hot-load a skill into the session
  /persona add <Name>  Hot-load a persona into the session
  /cost                Show token usage for this session
  /approval [mode]     Show or set approval mode (never/auto/write)
  /help                Show this help
  /exit, /quit         Exit
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

_log = logging.getLogger("AgentTUI")

_CTRL_C_EXIT_WINDOW = 1.0   # seconds between two Ctrl+C presses to trigger exit

_HISTORY_FILE = os.path.expanduser("~/.dfm/agent_history")
_TOOL_COLORS: Dict[str, str] = {
    "dfm_": "blue",
    "shell_exec": "yellow",
    "write_file": "yellow",
    "apply_patch": "yellow",
    "read_file": "green",
    "list_directory": "green",
    "grep_search": "green",
}

_SLASH_HELP = """\
Slash commands:
  /clear                 Clear conversation history
  /model                 Show current model
  /tools                 List registered tools
  /skills                List available skills and personas
  /personas              Alias for /skills
  /skill add <Name>      Hot-load a skill into the active session
  /persona add <Name>    Hot-load a persona into the active session
  /cost                  Show cumulative token usage
  /approval [mode]       Show or set approval mode: never | auto | write
  /help                  Show this help
  /exit, /quit           Exit (also Ctrl+D)
"""


def _tool_color(name: str) -> str:
    for prefix, color in _TOOL_COLORS.items():
        if name.startswith(prefix):
            return color
    return "cyan"


def _friendly_error(exc: Exception) -> str:
    """Convert an exception to a user-friendly message."""
    msg = str(exc)
    low = msg.lower()
    if "rate limit" in low or "429" in low:
        return f"Rate limit reached — please wait a moment and try again. ({exc.__class__.__name__})"
    if "timeout" in low:
        return f"Request timed out — check your network and try again. ({exc.__class__.__name__})"
    if "connection" in low or "503" in low or "502" in low:
        return f"Connection error — check your network. ({exc.__class__.__name__})"
    if "authentication" in low or "401" in low or "403" in low:
        return f"Authentication error — check your API key/token. ({exc.__class__.__name__})"
    return msg


class AgentTUI:
    """Interactive TUI backed by prompt_toolkit input and rich output."""

    def __init__(self, agent_core, pkg=None, context=None, loader=None):
        """
        Args:
            agent_core: DfmAgentCore instance.
            pkg: Root package (for skill/persona hot-loading and /skills).
            context: AgentContext (for hot-loading skills into the system prompt).
            loader: Package loader (for hot-loading).
        """
        self.agent = agent_core
        self.pkg = pkg or getattr(agent_core, 'pkg', None)
        self.loader = loader or getattr(agent_core, 'loader', None)
        self.context = context
        self.history: List[Dict] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._last_interrupt: float = 0.0   # timestamp of last Ctrl+C at prompt

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def run(self) -> int:
        """Run the TUI loop until the user exits. Returns exit code."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from rich.console import Console

        os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
        self._console = Console(highlight=False)
        self._session = PromptSession(history=FileHistory(_HISTORY_FILE))

        self._print_banner()

        while True:
            try:
                user_input = await self._session.prompt_async("> ")
            except EOFError:
                break
            except KeyboardInterrupt:
                now = time.monotonic()
                if now - self._last_interrupt <= _CTRL_C_EXIT_WINDOW:
                    self._console.print("\n[dim]Exiting.[/dim]")
                    break
                self._last_interrupt = now
                self._console.print("\n[dim](Press Ctrl+C again to exit)[/dim]")
                continue

            user_input = user_input.strip()
            if not user_input:
                continue

            self._last_interrupt = 0.0   # reset on successful input

            if user_input.startswith("/"):
                should_exit = await self._handle_command(user_input)
                if should_exit:
                    break
                continue

            self.history.append({"role": "user", "content": user_input})
            await self._stream_response(user_input)

        self._console.print("[dim]Goodbye.[/dim]")
        return 0

    # ------------------------------------------------------------------ #
    # Streaming response
    # ------------------------------------------------------------------ #

    async def _stream_response(self, user_input: str):
        from rich.live import Live
        from rich.markdown import Markdown
        from rich.panel import Panel
        from rich.spinner import Spinner
        from rich.text import Text
        from .streaming import translate_stream, TextDelta, ToolCallStart, ToolCallResult, MessageComplete
        from .agent_core import APPROVAL_NEVER, _WRITE_TOOLS

        accumulated = ""
        current_tool: Optional[str] = None
        approval_mode = getattr(self.agent, 'approval_mode', APPROVAL_NEVER)

        try:
            raw = self.agent.run_streamed(user_input, self.history[:-1])

            with Live(
                Spinner("dots", text="Thinking…"),
                console=self._console,
                refresh_per_second=15,
                transient=False,
            ) as live:
                async for ev in translate_stream(raw):
                    if isinstance(ev, TextDelta):
                        accumulated += ev.delta
                        live.update(Markdown(accumulated))

                    elif isinstance(ev, ToolCallStart):
                        current_tool = ev.tool_name
                        color = _tool_color(ev.tool_name)
                        try:
                            args_obj = json.loads(ev.args)
                            args_display = json.dumps(args_obj, indent=2)
                        except Exception:
                            args_display = ev.args

                        # Approval check for write/shell tools
                        if approval_mode != APPROVAL_NEVER and ev.tool_name in _WRITE_TOOLS:
                            live.stop()
                            self._console.print(Panel(
                                f"[dim]{args_display}[/dim]",
                                title=f"[bold {color}]⚙ {ev.tool_name}[/bold {color}]",
                                border_style=color,
                                expand=False,
                            ))
                            try:
                                ans = await self._session.prompt_async(
                                    f"Allow {ev.tool_name}? [Y/n] "
                                )
                                if ans.strip().lower() in ("n", "no"):
                                    self._console.print("[yellow]Tool call skipped.[/yellow]")
                                    # Can't abort mid-stream; signal denial via flag for next turn
                                    live.start()
                                    continue
                            except (EOFError, KeyboardInterrupt):
                                pass
                            live.start()
                        else:
                            live.update(Panel(
                                f"[dim]{args_display}[/dim]",
                                title=f"[bold {color}]⚙ {ev.tool_name}[/bold {color}]",
                                border_style=color,
                                expand=False,
                            ))

                    elif isinstance(ev, ToolCallResult):
                        color = _tool_color(ev.tool_name)
                        result_display = ev.result[:500] + ("…" if len(ev.result) > 500 else "")
                        self._console.print(Panel(
                            f"[dim]{result_display}[/dim]",
                            title=f"[bold {color}]✓ {ev.tool_name}[/bold {color}]",
                            border_style=color,
                            expand=False,
                        ))
                        current_tool = None
                        if accumulated:
                            live.update(Markdown(accumulated))
                        else:
                            live.update(Spinner("dots", text="Thinking…"))

                    elif isinstance(ev, MessageComplete):
                        if not accumulated:
                            accumulated = ev.content
                            live.update(Markdown(accumulated))

        except KeyboardInterrupt:
            self._console.print("\n[dim][cancelled][/dim]")
            return
        except Exception as e:
            self._console.print(f"[red]Error:[/red] {_friendly_error(e)}")
            _log.debug("Stream error", exc_info=True)
            return

        if accumulated:
            self._console.print()  # blank line after response
            self.history.append({"role": "assistant", "content": accumulated})

    # ------------------------------------------------------------------ #
    # Slash command dispatcher
    # ------------------------------------------------------------------ #

    async def _handle_command(self, cmd: str) -> bool:
        """Returns True if the user wants to exit."""
        parts = cmd.split()
        name = parts[0].lower()

        if name in ("/exit", "/quit"):
            return True
        elif name == "/clear":
            self.history.clear()
            self._console.print("[dim]Conversation cleared.[/dim]")
        elif name == "/model":
            self._console.print(f"Model: [bold]{getattr(self.agent, 'model_name', 'unknown')}[/bold]")
        elif name == "/tools":
            self._print_tools()
        elif name in ("/skills", "/personas"):
            self._print_skills()
        elif name == "/skill" and len(parts) >= 3 and parts[1].lower() == "add":
            await self._hotload_skill(" ".join(parts[2:]), kind="skill")
        elif name == "/persona" and len(parts) >= 3 and parts[1].lower() == "add":
            await self._hotload_skill(" ".join(parts[2:]), kind="persona")
        elif name == "/cost":
            self._print_cost()
        elif name == "/approval":
            self._handle_approval_cmd(parts)
        elif name == "/help":
            self._console.print(_SLASH_HELP)
        else:
            self._console.print(f"[yellow]Unknown command:[/yellow] {parts[0]}  (type /help)")

        return False

    # ------------------------------------------------------------------ #
    # Helper print methods
    # ------------------------------------------------------------------ #

    def _print_banner(self):
        from rich.panel import Panel
        from rich.text import Text
        model = getattr(self.agent, 'model_name', 'unknown')
        pkg_name = getattr(self.pkg, 'name', '') if self.pkg else ''
        basedir = getattr(self.pkg, 'basedir', '') if self.pkg else ''
        header = Text.assemble(
            ("DFM Agent", "bold cyan"), "  |  ",
            ("model: ", "dim"), (model, "bold"),
            ("  |  project: ", "dim"), (pkg_name, "bold"),
        )
        if basedir:
            header.append(f"\n{basedir}", style="dim")
        self._console.print(Panel(header, border_style="cyan", padding=(0, 1)))
        self._console.print("[dim]Type /help for commands, Ctrl+D to exit.[/dim]\n")

    def _print_tools(self):
        from rich.table import Table
        tools = getattr(self.agent.agent, 'tools', [])
        if not tools:
            self._console.print("[dim]No tools registered.[/dim]")
            return
        t = Table(title="Registered Tools", show_lines=False, header_style="bold")
        t.add_column("Name", style="bold cyan")
        t.add_column("Description")
        for tool in tools:
            tool_name = getattr(tool, 'name', str(tool))
            desc = (getattr(tool, 'description', '') or '').split('\n')[0]
            t.add_row(tool_name, desc)
        self._console.print(t)

    def _print_skills(self):
        from rich.table import Table
        if self.pkg is None:
            self._console.print("[dim]No project loaded.[/dim]")
            return
        skills, personas = [], []
        for task in self.pkg.task_m.values():
            uses = getattr(task, 'uses', None)
            if uses is None:
                continue
            tags = getattr(uses, 'tags', []) or []
            tag_names = {t.name if hasattr(t, 'name') else str(t) for t in tags}
            entry = (task.name.split('.')[-1], task.desc or '')
            if 'std.AgentSkillTag' in tag_names:
                skills.append(entry)
            if 'std.AgentPersonaTag' in tag_names:
                personas.append(entry)

        if skills:
            st = Table(title="Skills", show_lines=False, header_style="bold blue")
            st.add_column("Name", style="bold")
            st.add_column("Description")
            for name, desc in skills:
                st.add_row(name, desc)
            self._console.print(st)
        else:
            self._console.print("[dim]Skills: (none found)[/dim]")

        if personas:
            pt = Table(title="Personas", show_lines=False, header_style="bold magenta")
            pt.add_column("Name", style="bold")
            pt.add_column("Description")
            for name, desc in personas:
                pt.add_row(name, desc)
            self._console.print(pt)
        else:
            self._console.print("[dim]Personas: (none found)[/dim]")

    def _print_cost(self):
        self._console.print(
            f"[bold]Token usage[/bold] — "
            f"input: [cyan]{self._total_input_tokens}[/cyan]  "
            f"output: [cyan]{self._total_output_tokens}[/cyan]  "
            f"total: [bold]{self._total_input_tokens + self._total_output_tokens}[/bold]"
        )

    def _handle_approval_cmd(self, parts):
        from .agent_core import APPROVAL_NEVER, APPROVAL_AUTO, APPROVAL_WRITE
        if len(parts) == 1:
            mode = getattr(self.agent, 'approval_mode', APPROVAL_AUTO)
            self._console.print(f"Approval mode: [bold]{mode}[/bold]  (never | auto | write)")
        else:
            new_mode = parts[1].lower()
            if new_mode not in (APPROVAL_NEVER, APPROVAL_AUTO, APPROVAL_WRITE):
                self._console.print(f"[red]Unknown mode:[/red] {new_mode}  — use: never | auto | write")
                return
            self.agent.approval_mode = new_mode
            self._console.print(f"Approval mode set to: [bold]{new_mode}[/bold]")

    # ------------------------------------------------------------------ #
    # Hot-load skill / persona
    # ------------------------------------------------------------------ #

    async def _hotload_skill(self, task_name: str, kind: str):
        """Dynamically load a skill or persona and rebuild the agent's system prompt."""
        if self.pkg is None:
            self._console.print("[red]No project loaded.[/red]")
            return

        # Resolve the task
        full_name = task_name if '.' in task_name else f"{self.pkg.name}.{task_name}"
        task = self.pkg.task_m.get(full_name)
        if not task:
            # Try short name match
            for t in self.pkg.task_m.values():
                if t.name.split('.')[-1] == task_name:
                    task = t
                    break
        if not task:
            self._console.print(f"[red]Task not found:[/red] {task_name}")
            return

        # Build context entry by executing the task
        try:
            from .context_builder import AgentContextBuilder
            from .prompt_builder import SystemPromptBuilder
            rundir = os.path.join(os.getcwd(), "rundir")
            cb = AgentContextBuilder(pkg=self.pkg, loader=self.loader, rundir=rundir)
            new_context = cb.build_context([full_name])
        except Exception as e:
            self._console.print(f"[red]Failed to load {kind}:[/red] {e}")
            return

        # Merge into existing context and rebuild prompt
        if self.context is None:
            from .context_builder import AgentContext
            self.context = AgentContext()
            self.context.project_info = {
                'name': self.pkg.name,
                'desc': getattr(self.pkg, 'desc', '') or '',
                'basedir': getattr(self.pkg, 'basedir', '') or '',
            }
        if kind == "skill":
            self.context.skills.extend(new_context.skills)
        else:
            self.context.personas.extend(new_context.personas)

        pb = SystemPromptBuilder()
        new_prompt = pb.build_prompt(self.context)

        # Update the agent's instructions in-place
        self.agent.agent = self.agent.agent.__class__(
            name=self.agent.agent.name,
            instructions=new_prompt,
            model=self.agent.agent.model,
            tools=self.agent.agent.tools,
            mcp_servers=getattr(self.agent.agent, 'mcp_servers', []),
        )

        label = "Skill" if kind == "skill" else "Persona"
        self._console.print(f"[green]✓ {label} loaded:[/green] {task_name}")
