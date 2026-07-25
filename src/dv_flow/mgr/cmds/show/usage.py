#****************************************************************************
#* usage.py
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
"""The CLI-shaped view of a task: what you can pass it, not what it is.

One renderer, two entry points -- `dfm show task <name> --usage` and (once the
two-phase parse lands) `dfm run <task> --help`. Keeping it in one place is what
stops the two from drifting.
"""

from typing import Any, Dict, List, Optional

from .formatters import is_terminal
from ...task import collect_task_params, collect_param_value_sets


def _type_name(ptype) -> str:
    """A short, CLI-ish type name. `param_defs.types` holds real Python types
    (`<class 'int'>`), which is not what belongs in a usage line."""
    if ptype is None:
        return "any"
    name = getattr(ptype, '__name__', None)
    if name is None:
        name = str(ptype)
    return {
        'str': 'STR',
        'int': 'INT',
        'bool': 'BOOL',
        'float': 'FLOAT',
        'list': 'LIST',
        'dict': 'MAP',
    }.get(name, name.upper())


def _arg_label(a : Dict[str, Any]) -> str:
    """How the argument is named on the command line: its flags when it is a
    first-class option, otherwise the bare parameter name (settable with -D)."""
    if a['name'] is None:
        return a['param']
    if a['short']:
        return "%s, %s" % (a['short'], a['name'])
    return "    %s" % a['name']


def _choices_text(a : Dict[str, Any]) -> str:
    """'(quiet, normal, full)', or '(vlt, vcs, ...)' for an open set."""
    if not a.get('choices'):
        return ""
    text = ", ".join(str(c) for c in a['choices'])
    if a.get('choices_open'):
        text += ", ..."
    return "(%s)" % text


def _first_line(text : Optional[str]) -> str:
    if not text:
        return ""
    return text.strip().split('\n')[0]


def build_usage_info(task, prog : str = "dfm run") -> Dict[str, Any]:
    """Structured usage description of `task`.

    This is also the `--usage --json` document, so it is the contract a shell
    completion script, the vscode extension, or `dfm mcp` would consume. Keep it
    additive.

    `name`/`short` are `None` for a param with no first-class flag; `define`
    always holds the `-D` form, which works for every param.

    `choices` comes from the **parameter's** declared value set when it has one,
    because that is the set actually enforced -- on `-D` and on a `with:`
    override, not only on the flag. A `cli:` block's own `choices:` still wins,
    since it can only narrow what the flag accepts.
    """
    definitions, types = collect_task_params(task)
    value_sets = collect_param_value_sets(task)

    leaf = task.name.split('.')[-1] if '.' in task.name else task.name

    # Params promoted to first-class flags by a `cli:` block, keyed by param.
    from ...cli_args import resolve_task_cli
    cli = resolve_task_cli(task)
    flags = {}
    if cli is not None:
        for a in cli.args:
            flags[a.param or a.name] = a

    args : List[Dict[str, Any]] = []
    for pname in sorted(definitions.keys()):
        pdef = definitions[pname]
        default = getattr(pdef, 'value', None)
        flag = flags.get(pname)
        vs = value_sets.get(pname)
        choices = (flag.choices if (flag is not None and flag.choices is not None)
                   else (vs.values() if vs is not None else None))
        args.append({
            'name': ("--%s" % flag.name) if flag is not None else None,
            'short': ("-%s" % flag.short) if (flag is not None and flag.short) else None,
            'param': pname,
            'type': _type_name(types.get(pname)),
            'default': default,
            'help': _first_line((flag.help if flag is not None else None)
                                or getattr(pdef, 'doc', None)
                                or getattr(pdef, 'desc', None)),
            'choices': choices,
            # Per-value documentation, when the declaration supplies it. Kept
            # separate from `choices` so a consumer that only wants the values
            # is unaffected.
            'choices_doc': ([{'value': e.value, 'desc': e.desc} for e in vs.of]
                            if (vs is not None and any(e.desc for e in vs.of))
                            else None),
            # An open set enumerates the *known* values without forbidding the
            # rest; help must not present it as exhaustive.
            'choices_open': bool(vs.open) if vs is not None else False,
            'define': "-D %s.%s=VALUE" % (leaf, pname),
        })

    return {
        'task': task.name,
        'prog': prog,
        'desc': getattr(task, 'desc', '') or '',
        'doc': getattr(task, 'doc', '') or '',
        'usage': "%s %s [run-options]" % (prog, task.name),
        'args': args,
    }


def render_usage_text(info : Dict[str, Any]) -> str:
    """Plain-text rendering. No ANSI, so it is safe to pipe or golden-test."""
    lines = []

    heading = info['task']
    if info['desc']:
        heading += " — " + info['desc']
    lines.append(heading)
    lines.append("")
    lines.append("Usage: %s" % info['usage'])

    if info['doc']:
        lines.append("")
        for line in info['doc'].strip().split('\n'):
            lines.append(line)

    lines.append("")
    lines.append("Task arguments:")
    if info['args']:
        labels = [_arg_label(a) for a in info['args']]
        name_w = max(len(l) for l in labels)
        type_w = max(len(a['type']) for a in info['args'])
        for a, label in zip(info['args'], labels):
            default = a['default']
            default_s = ("[default: %s]" % default) if default not in (None, '') else ""
            line = "  %s  %s  %s" % (
                label.ljust(name_w), a['type'].ljust(type_w), default_s.ljust(20))
            if a['help']:
                line += "  " + a['help']
            if a['choices']:
                line += "  " + _choices_text(a)
            lines.append(line.rstrip())
            # Documented values get a line each: a value set is the only place
            # the meaning of 'quiet' vs 'normal' is written down, so hiding it
            # would leave the prose it replaced as the only explanation.
            for entry in (a.get('choices_doc') or []):
                if entry['desc']:
                    lines.append("  %s  %s" % (
                        str(entry['value']).rjust(name_w + 2), entry['desc']))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Set any task parameter with -D <task>.<param>=<value>, "
                 "or -D <param>=<value>")
    lines.append("to set it on every task that has it.")
    lines.append("Run `%s --help` for run options." % info['prog'])

    return "\n".join(lines)


def render_usage(task, prog : str = "dfm run"):
    """Render the usage view for `task` to stdout.

    Uses rich when stdout is a terminal and plain text otherwise, matching how
    every other `show` renderer behaves (`formatters.is_terminal`).
    """
    info = build_usage_info(task, prog)

    if not is_terminal():
        print(render_usage_text(info))
        return info

    from rich.console import Console
    from rich.table import Table

    console = Console()

    heading = "[bold cyan]%s[/bold cyan]" % info['task']
    if info['desc']:
        heading += " — %s" % info['desc']
    console.print(heading)
    console.print()
    console.print("[bold]Usage:[/bold] %s" % info['usage'])

    if info['doc']:
        console.print()
        console.print(info['doc'].strip())

    console.print()
    console.print("[bold yellow]Task arguments:[/bold yellow]")
    if info['args']:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Argument", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Default", style="yellow")
        table.add_column("Description", style="dim")
        for a in info['args']:
            default = a['default']
            help_s = a['help'] or ""
            if a['choices']:
                help_s += "  " + _choices_text(a)
            for entry in (a.get('choices_doc') or []):
                if entry['desc']:
                    help_s += "\n  [cyan]%s[/cyan]  %s" % (
                        entry['value'], entry['desc'])
            table.add_row(_arg_label(a).strip(), a['type'],
                          str(default) if default not in (None, '') else '-',
                          help_s)
        console.print(table)
    else:
        console.print("[dim]  (none)[/dim]")

    console.print()
    console.print("[dim]Set any task parameter with -D <task>.<param>=<value>, "
                  "or -D <param>=<value> to set it on every task that has it.[/dim]")
    console.print("[dim]Run `%s --help` for run options.[/dim]" % info['prog'])

    return info
