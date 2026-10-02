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


def build_usage_info(task, prog : str = "dfm run",
                     values : Dict[str, Any] = None) -> Dict[str, Any]:
    """Structured usage description of `task`.

    `values`, when supplied, holds each parameter's RESOLVED value (see
    `TaskGraphBuilder.resolveTaskParams`). Without it the declared `value:` is
    shown, which for a lazily-evaluated default is its source text -- so a
    parameter declared `value: "${{ build }}"` reads `[default: ${{ build }}]`
    instead of `[default: opt]`. Optional so the document can still be built
    without a loaded project.

    This is also the `--usage --json` document, so it is the contract a shell
    completion script, the vscode extension, or `dfm mcp` would consume. Keep it
    additive.

    `name`/`short` are `None` for a param with no first-class flag; `define`
    always holds the `-D` form, which works for every param.

    `choices` comes from the **parameter's** declared value set when it has one,
    because that is the set actually enforced -- on `-D` and on a `with:`
    override, not only on the flag.
    """
    definitions, types = collect_task_params(task)
    value_sets = collect_param_value_sets(task)

    leaf = task.name.split('.')[-1] if '.' in task.name else task.name

    # Params exposed as first-class flags by their own declaration, keyed by param.
    from ...cli_args import resolve_task_cli
    flags = {a.param: a for a in resolve_task_cli(task) if not a.hidden}

    args : List[Dict[str, Any]] = []
    for pname in sorted(definitions.keys()):
        pdef = definitions[pname]
        default = getattr(pdef, 'value', None)
        if values is not None and pname in values:
            default = values[pname]
        flag = flags.get(pname)
        vs = value_sets.get(pname)
        choices = vs.values() if vs is not None else None
        args.append({
            'name': ("--%s" % flag.name) if flag is not None else None,
            'short': ("-%s" % flag.short) if (flag is not None and flag.short) else None,
            'param': pname,
            'type': _type_name(types.get(pname)),
            'default': default,
            # `desc` first -- a one-line help slot wants the one-line
            # summary, not the opening line of prose written to be read in
            # paragraphs. Same order as CliArg.help.
            'help': _first_line(getattr(pdef, 'desc', None)
                                or getattr(pdef, 'doc', None)),
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


def render_usage(task, prog : str = "dfm run", values : Dict[str, Any] = None):
    """Render the usage view for `task` to stdout.

    Uses rich when stdout is a terminal and plain text otherwise, matching how
    every other `show` renderer behaves (`formatters.is_terminal`).
    """
    info = build_usage_info(task, prog, values=values)

    if not is_terminal():
        print(render_usage_text(info))
        return info

    from rich.table import Table

    from ...tui_theme import make_console, S_LABEL, S_SECONDARY

    console = make_console()

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
        # The description is the column the reader came for; the column
        # position already marks it as secondary -- see tui_theme.
        table.add_column("Description", style=S_SECONDARY)
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
        # The answer to "what arguments?" -- read, so not `dim`.
        console.print("[%s]  (none)[/%s]" % (S_SECONDARY, S_SECONDARY))

    console.print()
    # Usage hints: the reader acts on these, so they take a named colour.
    console.print(
        "[%s]Set any task parameter with -D <task>.<param>=<value>, "
        "or -D <param>=<value> to set it on every task that has it.[/%s]"
        % (S_LABEL, S_LABEL))
    console.print("[%s]Run `%s --help` for run options.[/%s]"
                  % (S_LABEL, info['prog'], S_LABEL))

    return info


def build_package_options(pkg, loader=None) -> List[Dict[str, Any]]:
    """The project-level options `pkg` exposes -- package variables declared
    `cli:` -- in the same shape `build_usage_info` uses for task arguments.

    Structured rather than pre-rendered because two callers show these: the
    no-task listing of `dfm run` and the `Project options` block of
    `dfm run <task> --help`.
    """
    from ...cli_args import collect_package_cli

    ret : List[Dict[str, Any]] = []
    for a in collect_package_cli(pkg, loader):
        if a.hidden:
            continue
        label = "--%s" % a.name
        if a.short:
            label = "-%s, %s" % (a.short, label)
        # A package variable has no `uses:` chain of parameter definitions, so
        # its declaration is the only source of the value set -- the same
        # reasoning as the `choices` fallback in `build_arg_parser`.
        vs = getattr(a.pdef, 'values', None)
        ret.append({
            'label': label,
            'param': a.param,
            'default': a.default,
            'help': _first_line(getattr(a.pdef, 'desc', None)
                                or getattr(a.pdef, 'doc', None)),
            'choices': vs.values() if vs is not None else None,
            'choices_doc': ([{'value': e.value, 'desc': e.desc} for e in vs.of]
                            if (vs is not None and any(e.desc for e in vs.of))
                            else None),
            'choices_open': bool(vs.open) if vs is not None else False,
        })
    return ret


def render_package_options_text(pkg_name : str,
                                options : List[Dict[str, Any]]) -> List[str]:
    """Plain-text lines for `build_package_options`, heading included.

    Empty list when the project exposes nothing, so a caller can splice the
    result in unconditionally.
    """
    if not options:
        return []
    lines = ["Project options (apply to any task in %s):" % pkg_name]
    label_w = max(len(o['label']) for o in options)
    for o in options:
        line = "  %s  %s" % (o['label'].ljust(label_w), o['help'] or "")
        if o['default'] not in (None, ''):
            line += " (default: %s)" % o['default']
        lines.append(line.rstrip())
        if o['choices'] and not o['choices_doc']:
            lines.append("  %s  %s" % (
                " ".ljust(label_w), _choices_text(o)))
        for entry in (o['choices_doc'] or []):
            lines.append("  %s  %s%s" % (
                str(entry['value']).rjust(label_w),
                "- " if entry['desc'] else "",
                entry['desc'] or ""))
    return lines
