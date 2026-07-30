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
"""Resolution, validation and parsing of a task's command-line arguments.

A parameter that should be settable from the command line says so **in its own
declaration** -- `cli: true` on the `ParamDef`. There is no separate `cli:`
block: type, default, help text and accepted values are already on the
parameter, so a block could only restate them (and drift from them).

The parse is necessarily two-phase: which flags a task accepts is only knowable
once the flow has loaded, so `dfm run` takes the run options with
`parse_known_args` and hands the leftovers here.
"""

import argparse
import dataclasses as dc
from typing import Any, Dict, List, Optional, Tuple

from .param_types import TypeKind, normalize_type
from .task import (iter_uses_chain, collect_task_params,
                   collect_param_value_sets, collect_param_cli)


@dc.dataclass
class CliArg(object):
    """One command-line option of a task, resolved from the parameter that
    declares it. Everything but `param`/`short`/`hidden` is read back off the
    `ParamDef`, so there is exactly one place a flag's shape is stated."""
    name : str                  # long-option name, without '--'
    param : str                 # the parameter it sets
    short : str = None
    hidden : bool = False
    pdef : Any = None           # the declaring ParamDef
    type : Any = None           # the parameter's declared type

    @property
    def help(self):
        if self.pdef is None:
            return None
        return getattr(self.pdef, 'doc', None) or getattr(self.pdef, 'desc', None)

    @property
    def default(self):
        return getattr(self.pdef, 'value', None) if self.pdef is not None else None


_reserved_cache = None


def reserved_options() -> set:
    """Option strings a task's parameters may not claim as flags.

    Derived from the actual parsers rather than hand-listed. That is what makes
    accepting bare task args safe: adding a run option later turns any colliding
    parameter declaration into a load-time marker instead of silently stealing
    the flag.
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


def resolve_task_cli(task) -> List[CliArg]:
    """The command-line options `task` accepts, in declaration order.

    One `CliArg` per parameter whose declaration carries `cli:`, collected along
    the `uses:` chain per parameter (see `collect_param_cli`). Returns an empty
    list for a task that exposes nothing.
    """
    if task is None:
        return []
    opts = collect_param_cli(task)
    if not opts:
        return []
    definitions, types = collect_task_params(task)

    # Declaration order, base params first -- `collect_param_cli` preserves it.
    # Alphabetical would reorder a task's help for no reason.
    args = []
    for param, opt in opts.items():
        args.append(CliArg(
            # The flag is the parameter's own name, verbatim. No underscore-to-
            # dash rewriting: a silent rename makes the flag and the `-D` form
            # of the same parameter disagree, and `name:` covers the rare case.
            name=(getattr(opt, 'name', None) or param),
            param=param,
            short=getattr(opt, 'short', None),
            hidden=bool(getattr(opt, 'hidden', False)),
            pdef=definitions.get(param),
            type=types.get(param)))
    return args


def collect_package_cli(pkg, loader=None) -> List[CliArg]:
    """The command-line options the PROJECT exposes -- package variables whose
    declaration carries `cli:`.

    A package variable is a project-wide knob rather than one task's argument,
    so its flag applies to every `dfm run` in that project. Collected along the
    package `uses:` chain so a base project can define an interface its leaves
    inherit -- the same reason task params inherit their flags.

    Returns [] when nothing is exposed, which is the common case.
    """
    if pkg is None:
        return []

    seen = set()
    chain = []
    current = pkg
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        pkg_def = getattr(current, 'pkg_def', None)
        base_name = getattr(pkg_def, 'uses', None) if pkg_def else None
        current = None
        if base_name and loader is not None:
            current = getattr(loader, '_pkg_m', {}).get(base_name)

    # Base-first, so a leaf redeclaring a variable wins -- and `cli: false`
    # lets it withdraw a flag its base offered.
    opts = {}
    for p in reversed(chain):
        pkg_def = getattr(p, 'pkg_def', None)
        params = getattr(pkg_def, 'params', None) or {}
        for name, pdef in params.items():
            cli = getattr(pdef, 'cli', None)
            if cli is None:
                continue
            if cli is False:
                opts.pop(name, None)
            else:
                opts[name] = (cli, pdef)

    args = []
    for name, (opt, pdef) in opts.items():
        ptype = None
        paramT = getattr(pkg, 'paramT', None)
        if paramT is not None and name in getattr(paramT, 'model_fields', {}):
            ptype = paramT.model_fields[name].annotation
        args.append(CliArg(
            name=(getattr(opt, 'name', None) or name),
            param=name,
            short=getattr(opt, 'short', None),
            hidden=bool(getattr(opt, 'hidden', False)),
            pdef=pdef,
            type=ptype))
    return args


def validate_package_cli(pkg, loader, error) -> None:
    """Check the flags a package exposes, reporting through `error`."""
    args = collect_package_cli(pkg, loader)
    if not args:
        return
    reserved = reserved_options()
    seen_names = {}
    seen_shorts = {}
    for arg in args:
        opt = "--%s" % arg.name
        if arg.name in seen_names:
            error("package '%s' exposes '%s' twice (variables '%s' and '%s')" % (
                pkg.name, opt, seen_names[arg.name].param, arg.param))
        seen_names[arg.name] = arg
        if opt in reserved:
            error("package variable '%s' asks to be exposed as '%s', which "
                  "collides with the dfm option of the same name. Rename the "
                  "flag with `cli: {name: ...}`." % (arg.param, opt))
        if arg.short:
            if len(arg.short) != 1:
                error("package variable '%s': 'short' must be a single "
                      "character, got '%s'" % (arg.param, arg.short))
                continue
            sopt = "-%s" % arg.short
            if arg.short in seen_shorts:
                error("package '%s' exposes short option '%s' twice" % (
                    pkg.name, sopt))
            seen_shorts[arg.short] = arg
            if sopt in reserved:
                error("package variable '%s': short option '%s' collides with "
                      "a dfm option" % (arg.param, sopt))


_KIND_NAME = {
    TypeKind.STR: 'str',
    TypeKind.INT: 'int',
    TypeKind.FLOAT: 'float',
    TypeKind.BOOL: 'bool',
    TypeKind.LIST: 'list',
    TypeKind.MAP: 'map',
}


def _type_kind(param_type) -> str:
    """'str' | 'int' | 'float' | 'bool' | 'list' | 'map'.

    Goes through `normalize_type` rather than inspecting the type object,
    because dfm encodes a list param as `Union[str, List]` -- which has neither
    a useful `__name__` nor a `list` origin.
    """
    return _KIND_NAME.get(normalize_type(param_type), 'str')


def validate_task_cli(task, error) -> None:
    """Check the flags `task` exposes, reporting problems through `error`.

    Problems are reported as markers, never exceptions: a `cli:` that cannot
    work is a flow-authoring mistake and should read like every other load
    diagnostic.

    Note this validates the task's *effective* flag set, inherited ones
    included: a collision can be created by inheritance alone (a base exposing
    `--force` was fine until `dfm` grew that option), and the task that has to
    deal with it is this one.
    """
    args = resolve_task_cli(task)
    if not args:
        return

    reserved = reserved_options()
    seen_names = {}
    seen_shorts = {}

    for arg in args:
        opt = "--%s" % arg.name
        if arg.name in seen_names:
            error("task '%s' exposes '%s' twice (parameters '%s' and '%s')" % (
                task.name, opt, seen_names[arg.name].param, arg.param))
        seen_names[arg.name] = arg
        if opt in reserved:
            error("parameter '%s' on task '%s' asks to be exposed as '%s', which "
                  "collides with the dfm option of the same name. Rename the "
                  "flag with `cli: {name: ...}`." % (arg.param, task.name, opt))

        if arg.short:
            if len(arg.short) != 1:
                error("parameter '%s' on task '%s': 'short' must be a single "
                      "character, got '%s'" % (arg.param, task.name, arg.short))
                continue
            sopt = "-%s" % arg.short
            if arg.short in seen_shorts:
                error("task '%s' exposes short option '%s' twice (parameters "
                      "'%s' and '%s')" % (
                          task.name, sopt, seen_shorts[arg.short].param, arg.param))
            seen_shorts[arg.short] = arg
            if sopt in reserved:
                error("parameter '%s' on task '%s': short option '%s' collides "
                      "with a dfm option" % (arg.param, task.name, sopt))


def build_arg_parser(task, args : List[CliArg], prog : str,
                     values : Dict[str, Any] = None) -> Tuple[
        argparse.ArgumentParser, Dict[str, str]]:
    """An argparse parser for `args`, plus a dest -> param-name map.

    `values` holds each parameter's RESOLVED value, used for the `(default: ...)`
    text. Without it a lazily-evaluated default prints as its source expression.
    It never changes what the parser *does*: every flag still defaults to None
    so "not given" stays distinguishable from "given the default".

    `task` may also be a Package, for the project-level flags -- it is only used
    to look up inherited value sets, and a package has none to inherit.
    """
    value_sets = collect_param_value_sets(task)

    parser = argparse.ArgumentParser(
        prog=prog,
        description=getattr(task, 'desc', '') or None,
        add_help=False)
    dest_param = {}

    for arg in args:
        param = arg.param
        kind = _type_kind(arg.type)

        flags = ["--%s" % arg.name]
        if arg.short:
            flags.insert(0, "-%s" % arg.short)

        dest = "arg_%s" % arg.name.replace('-', '_')
        dest_param[dest] = param

        help_text = argparse.SUPPRESS if arg.hidden else arg.help
        default = arg.default
        if values is not None and param in values:
            default = values[param]

        kwargs = {'dest': dest, 'default': None, 'help': help_text}
        # The parameter's declared type decides how the flag behaves: a bool is
        # a switch, a list collects. There is no `action:` to state separately.
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
            # Choices come from the parameter's own value set. Only for a closed
            # scalar set: an open set must not block an unlisted value, and a
            # list arg is collected before `--views a,b` is comma-split, so
            # argparse would reject the joined string. Both still get checked --
            # a task flag binds through the override map, which runs the same
            # value-set check as `-D`.
            # The inheritance-aware set first (a derived task may narrow it),
            # then the declaration the flag came from -- which is the only
            # source for a package variable, since a package has no `uses:`
            # chain of parameter definitions to walk.
            vs = value_sets.get(param)
            if vs is None:
                vs = getattr(arg.pdef, 'values', None)
            if (vs is not None and not vs.open
                    and kind not in ('list', 'map')):
                kwargs['choices'] = vs.values()
            if arg.hidden:
                pass
            elif help_text is not None and default is not None:
                kwargs['help'] = "%s (default: %s)" % (help_text, default)
            elif default is not None:
                kwargs['help'] = "(default: %s)" % (default,)

        parser.add_argument(*flags, **kwargs)

    return parser, dest_param


def parse_task_args(task, args : List[CliArg], argv : List[str],
                    prog : str, partial : bool = False,
                    values : Dict[str, Any] = None):
    """Parse `argv` against `args` -> {param: value}.

    Only params the user actually supplied are returned, so an unmentioned flag
    leaves the parameter's own default (or a `-D` override) in place. Exits with
    a task-scoped usage message on a bad argument, exactly as argparse would for
    any other command.

    `partial=True` returns `(values, unconsumed-argv)` and leaves an unknown
    flag alone instead of erroring -- used for the project-level pass, where the
    tokens it does not recognize belong to the task and only the task's parser
    can say what is accepted.
    """
    parser, dest_param = build_arg_parser(task, args, prog, values=values)
    if partial:
        ns, remaining = parser.parse_known_args(argv)
    else:
        ns = parser.parse_args(argv)
    ret = {}
    for dest, param in dest_param.items():
        value = getattr(ns, dest, None)
        if value is not None:
            ret[param] = _split_list_values(value)
    return (ret, remaining) if partial else ret


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
