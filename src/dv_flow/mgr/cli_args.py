#****************************************************************************
#* cli_args.py
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
"""Resolution, validation and parsing of a task's `cli:` arguments.

The parse is necessarily two-phase: which flags a task accepts is only knowable
once the flow has loaded, so `dfm run` takes the run options with
`parse_known_args` and hands the leftovers here.
"""

import argparse
from typing import Any, Dict, List, Optional, Tuple

from .cli_def import CliArgDef, CliDef
from .param_types import TypeKind, normalize_type
from .task import (iter_uses_chain, collect_task_params,
                   collect_param_value_sets)


_reserved_cache = None


def reserved_options() -> set:
    """Option strings a task's `cli:` block may not claim.

    Derived from the actual parsers rather than hand-listed. That is what makes
    accepting bare task args safe: adding a run option later turns any colliding
    `cli:` block into a load-time marker instead of silently stealing the flag.
    Spans the global parser too -- `-D`/`-P`/`--log-level`/`--package-map` are
    declared there as well as on the subcommand.
    """
    global _reserved_cache
    if _reserved_cache is None:
        from .__main__ import get_parser, reserved_option_strings
        parser = get_parser()
        parsers = [parser]
        for action in getattr(parser, '_subparsers')._group_actions:
            choices = getattr(action, 'choices', None) or {}
            if 'run' in choices:
                parsers.append(choices['run'])
        _reserved_cache = reserved_option_strings(*parsers)
    return _reserved_cache


def resolve_task_cli(task) -> Optional[CliDef]:
    """The `cli:` block in effect for `task`.

    Walks the `uses:` chain, nearest declaration winning, with **whole-block
    replacement**. Params already inherit along `uses:`, and a `cli:` block
    references params, so a derived task that inherited `seed` but lost `--seed`
    would be indefensible. Replacement rather than per-arg merge because merging
    immediately raises "how do I delete an inherited flag?".
    """
    if task is None:
        return None
    for current in iter_uses_chain(task):
        cli = getattr(current, 'cli', None)
        if cli:
            return cli
    return None


_KIND_NAME = {
    TypeKind.STR: 'str',
    TypeKind.INT: 'int',
    TypeKind.FLOAT: 'float',
    TypeKind.BOOL: 'bool',
    TypeKind.LIST: 'list',
    TypeKind.MAP: 'map',
}


def _type_kind(arg : CliArgDef, param_type) -> str:
    """'str' | 'int' | 'float' | 'bool' | 'list' | 'map'.

    An explicit `type:` on the arg wins; otherwise the parameter's declared type
    decides. Goes through `normalize_type` rather than inspecting the type
    object, because dfm encodes a list param as `Union[str, List]` -- which has
    neither a useful `__name__` nor a `list` origin.
    """
    if arg.type:
        return arg.type
    return _KIND_NAME.get(normalize_type(param_type), 'str')


def validate_task_cli(task, error) -> None:
    """Check a task's own `cli:` block, reporting problems through `error`.

    Problems are reported as markers, never exceptions: a bad `cli:` block is a
    flow-authoring mistake and should read like every other load diagnostic.
    Validates the task's *own* declaration only -- an inherited block was already
    validated on the task that declared it.
    """
    cli = getattr(task, 'cli', None)
    if not cli:
        return

    definitions, _ = collect_task_params(task)
    reserved = reserved_options()
    seen_names = {}
    seen_shorts = {}

    for arg in cli.args:
        param = arg.param or arg.name
        if param not in definitions:
            error("cli arg '%s' on task '%s' names parameter '%s', which the task "
                  "does not have. Available parameters: %s" % (
                      arg.name, task.name, param, sorted(definitions.keys())))

        opt = "--%s" % arg.name
        if arg.name in seen_names:
            error("cli arg '%s' is declared twice on task '%s'" % (arg.name, task.name))
        seen_names[arg.name] = arg
        if opt in reserved:
            error("cli arg '%s' on task '%s' collides with the dfm option '%s'" % (
                arg.name, task.name, opt))

        if arg.short:
            if len(arg.short) != 1:
                error("cli arg '%s' on task '%s': 'short' must be a single "
                      "character, got '%s'" % (arg.name, task.name, arg.short))
                continue
            sopt = "-%s" % arg.short
            if arg.short in seen_shorts:
                error("cli arg short option '%s' is declared twice on task '%s'" % (
                    sopt, task.name))
            seen_shorts[arg.short] = arg
            if sopt in reserved:
                error("cli arg '%s' on task '%s': short option '%s' collides with "
                      "a dfm option" % (arg.name, task.name, sopt))


def build_arg_parser(task, cli : CliDef, prog : str) -> Tuple[argparse.ArgumentParser,
                                                              Dict[str, str]]:
    """An argparse parser for `cli.args`, plus a dest -> param-name map."""
    definitions, types = collect_task_params(task)
    value_sets = collect_param_value_sets(task)

    parser = argparse.ArgumentParser(
        prog=prog,
        description=getattr(task, 'desc', '') or None,
        add_help=False)
    dest_param = {}

    for arg in cli.args:
        param = arg.param or arg.name
        pdef = definitions.get(param)
        kind = _type_kind(arg, types.get(param))

        flags = ["--%s" % arg.name]
        if arg.short:
            flags.insert(0, "-%s" % arg.short)

        dest = "arg_%s" % arg.name.replace('-', '_')
        dest_param[dest] = param

        help_text = arg.help
        if help_text is None and pdef is not None:
            help_text = getattr(pdef, 'doc', None) or getattr(pdef, 'desc', None)

        default = arg.default
        if default is None and pdef is not None:
            default = getattr(pdef, 'value', None)

        kwargs = {'dest': dest, 'default': None, 'help': help_text}
        action = arg.action
        if action is None:
            action = {'bool': 'store_true', 'list': 'append'}.get(kind)

        if action == 'store_true':
            kwargs['action'] = 'store_true'
            # `default=None` keeps "not given" distinguishable from "given
            # false", so an unset flag leaves the param's own default alone.
            kwargs['default'] = None
        elif action == 'count':
            kwargs['action'] = 'count'
        else:
            if action == 'append':
                kwargs['action'] = 'append'
            # Without this argparse derives the metavar from `dest`, which is
            # mangled to avoid collisions -- users would see `--seed ARG_SEED`.
            kwargs['metavar'] = arg.name.upper().replace('-', '_')
            if kind == 'int':
                kwargs['type'] = int
            elif kind == 'float':
                kwargs['type'] = float
            choices = arg.choices
            if choices is None:
                # Default from the parameter's own value set. Only for a closed
                # scalar set: an open set must not block an unlisted value, and
                # a list arg is collected before `--views a,b` is comma-split,
                # so argparse would reject the joined string. Both still get
                # checked -- a task flag binds through the override map, which
                # runs the same value-set check as `-D`.
                vs = value_sets.get(param)
                if (vs is not None and not vs.open
                        and kind not in ('list', 'map')):
                    choices = vs.values()
            if choices is not None:
                kwargs['choices'] = choices
            if help_text is not None and default is not None:
                kwargs['help'] = "%s (default: %s)" % (help_text, default)
            elif default is not None:
                kwargs['help'] = "(default: %s)" % (default,)

        parser.add_argument(*flags, **kwargs)

    return parser, dest_param


def parse_task_args(task, cli : CliDef, argv : List[str],
                    prog : str) -> Dict[str, Any]:
    """Parse `argv` against the task's `cli:` block -> {param: value}.

    Only params the user actually supplied are returned, so an unmentioned flag
    leaves the parameter's own default (or a `-D` override) in place. Exits with
    a task-scoped usage message on a bad argument, exactly as argparse would for
    any other command.
    """
    parser, dest_param = build_arg_parser(task, cli, prog)
    ns = parser.parse_args(argv)
    ret = {}
    for dest, param in dest_param.items():
        value = getattr(ns, dest, None)
        if value is not None:
            ret[param] = _split_list_values(value)
    return ret


def _split_list_values(value):
    """Comma-split the elements of an `append`-collected list argument.

    A list param is collected with `action='append'`, so `--tests a --tests b`
    already yields `['a', 'b']` -- but `--tests a,b` yielded `['a,b']`, while
    `-D tests=a,b` yields `['a', 'b']` (engine-wide policy in
    `param_types.coerce_cli_value`). Two spellings of the same override
    disagreeing is a trap, so the comma is honored on both paths.
    """
    if not isinstance(value, list):
        return value
    ret = []
    for v in value:
        if isinstance(v, str) and "," in v:
            ret.extend(s.strip() for s in v.split(",") if s.strip())
        else:
            ret.append(v)
    return ret
