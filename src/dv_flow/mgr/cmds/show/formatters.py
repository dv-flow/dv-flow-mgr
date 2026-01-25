#****************************************************************************
#* formatters.py
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
"""Output formatters for show commands."""

import json
import sys
from typing import List, Dict, Any, Optional


def is_terminal() -> bool:
    """Check if stdout is a terminal (not redirected to file/pipe)."""
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


class TableFormatter:
    """Format tabular output for terminal display."""
    
    def __init__(self, columns: List[str], min_widths: Optional[List[int]] = None):
        self._columns = columns
        self._min_widths = min_widths or [10] * len(columns)
        self._rows: List[List[str]] = []
    
    def add_row(self, values: List[str]):
        """Add a row to the table."""
        self._rows.append([str(v) if v is not None else '' for v in values])
    
    def render(self) -> str:
        """Render the table as a string."""
        if not self._rows:
            return "No results found."
        
        # Calculate column widths
        widths = list(self._min_widths)
        for i, col in enumerate(self._columns):
            widths[i] = max(widths[i], len(col))
        for row in self._rows:
            for i, val in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(val))
        
        # Build output
        lines = []
        
        # Header
        header = "  ".join(col.ljust(widths[i]) for i, col in enumerate(self._columns))
        lines.append(header)
        
        # Separator
        separator = "  ".join("-" * widths[i] for i in range(len(self._columns)))
        lines.append(separator)
        
        # Rows
        for row in self._rows:
            line = "  ".join(
                (row[i] if i < len(row) else '').ljust(widths[i]) 
                for i in range(len(self._columns))
            )
            lines.append(line)
        
        return "\n".join(lines)
    
    def print(self):
        """Print the table, using rich formatting if output is a terminal."""
        if is_terminal():
            self._print_rich()
        else:
            print(self.render())
    
    def _print_rich(self):
        """Print using rich library for enhanced terminal output."""
        from rich.console import Console
        from rich.table import Table
        from rich.style import Style
        
        console = Console()
        
        if not self._rows:
            console.print("[dim]No results found.[/dim]")
            return
        
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            row_styles=["", "dim"],
        )
        
        for col in self._columns:
            table.add_column(col)
        
        for row in self._rows:
            table.add_row(*row)
        
        console.print(table)


class JsonFormatter:
    """Format output as JSON for Agent consumption."""
    
    def __init__(self, command: str, filters: Optional[Dict[str, Any]] = None):
        self._command = command
        self._filters = filters or {}
        self._results: List[Dict[str, Any]] = []
    
    def set_results(self, results: List[Dict[str, Any]]):
        """Set the results list."""
        self._results = results
    
    def render(self) -> str:
        """Render as JSON string."""
        output = {
            "command": self._command,
            "filters": self._filters,
            "results": self._results,
            "count": len(self._results)
        }
        return json.dumps(output, indent=2)


class DetailFormatter:
    """Format detailed single-item output."""
    
    def __init__(self):
        self._sections: List[tuple] = []
    
    def add_field(self, name: str, value: Any):
        """Add a simple field."""
        self._sections.append(('field', name, value))
    
    def add_section(self, title: str, content: str):
        """Add a multi-line section."""
        self._sections.append(('section', title, content))
    
    def add_list(self, title: str, items: List[str]):
        """Add a list section."""
        self._sections.append(('list', title, items))
    
    def add_params(self, title: str, params: Dict[str, Dict[str, Any]]):
        """Add a parameters section."""
        self._sections.append(('params', title, params))
    
    def render(self) -> str:
        """Render the detail view."""
        lines = []
        
        for section in self._sections:
            kind = section[0]
            
            if kind == 'field':
                name, value = section[1], section[2]
                if value is not None and value != '':
                    lines.append(f"{name}: {value}")
            
            elif kind == 'section':
                title, content = section[1], section[2]
                lines.append(f"\n{title}:")
                if content:
                    for line in content.strip().split('\n'):
                        lines.append(f"  {line}")
                else:
                    lines.append("  (none)")
            
            elif kind == 'list':
                title, items = section[1], section[2]
                lines.append(f"\n{title}:")
                if items:
                    for item in items:
                        lines.append(f"  - {item}")
                else:
                    lines.append("  (none)")
            
            elif kind == 'params':
                title, params = section[1], section[2]
                lines.append(f"\n{title}:")
                if params:
                    # Calculate max name width
                    max_name = max(len(n) for n in params.keys()) if params else 0
                    for name, info in params.items():
                        ptype = info.get('type', 'any')
                        default = info.get('value', '')
                        doc = info.get('doc', '')
                        line = f"  {name.ljust(max_name)} : {ptype}"
                        if default != '' and default is not None:
                            line += f" = {default}"
                        if doc:
                            # First line of doc as comment
                            doc_line = doc.strip().split('\n')[0][:40]
                            line += f"  # {doc_line}"
                        lines.append(line)
                else:
                    lines.append("  (none)")
        
        return "\n".join(lines)
    
    def print(self):
        """Print the detail view, using rich formatting if output is a terminal."""
        if is_terminal():
            self._print_rich()
        else:
            print(self.render())
    
    def _print_rich(self):
        """Print using rich library for enhanced terminal output."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich.markdown import Markdown
        
        console = Console()
        
        for section in self._sections:
            kind = section[0]
            
            if kind == 'field':
                name, value = section[1], section[2]
                if value is not None and value != '':
                    console.print(f"[bold cyan]{name}:[/bold cyan] {value}")
            
            elif kind == 'section':
                title, content = section[1], section[2]
                console.print(f"\n[bold yellow]{title}:[/bold yellow]")
                if content:
                    # Check if content looks like markdown
                    if '```' in content or content.strip().startswith('#'):
                        console.print(Markdown(content))
                    else:
                        console.print(Panel(content.strip(), border_style="dim"))
                else:
                    console.print("[dim]  (none)[/dim]")
            
            elif kind == 'list':
                title, items = section[1], section[2]
                console.print(f"\n[bold yellow]{title}:[/bold yellow]")
                if items:
                    for item in items:
                        console.print(f"  [green]•[/green] {item}")
                else:
                    console.print("[dim]  (none)[/dim]")
            
            elif kind == 'params':
                title, params = section[1], section[2]
                console.print(f"\n[bold yellow]{title}:[/bold yellow]")
                if params:
                    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
                    table.add_column("Name", style="cyan")
                    table.add_column("Type", style="green")
                    table.add_column("Default", style="yellow")
                    table.add_column("Description", style="dim")
                    
                    for name, info in params.items():
                        ptype = info.get('type', 'any')
                        default = str(info.get('value', '')) if info.get('value') not in (None, '') else '-'
                        doc = info.get('doc', '')
                        if doc:
                            doc = doc.strip().split('\n')[0][:40]
                        table.add_row(name, str(ptype), default, doc)
                    
                    console.print(table)
                else:
                    console.print("[dim]  (none)[/dim]")
