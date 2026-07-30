"""
Tab-completion helper for shells (bash, zsh, fish).

Usage from a shell completion function::

    dfm complete <prefix>              # task names
    dfm complete --task <name> <prefix>  # that task's --flags

Prints one candidate per line, suitable for consumption by shell completion.
"""

import logging
import os
import sys
from typing import ClassVar
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..cli_task_resolver import CLITaskResolver
from .util import get_rootdir


class CmdComplete:
    _log: ClassVar = logging.getLogger("CmdComplete")

    def __call__(self, args):
        prefix = getattr(args, 'prefix', '') or ''

        try:
            loader, pkg = loadProjPkgDef(
                get_rootdir(args),
                config=getattr(args, 'config', None),
                package_maps=getattr(args, 'package_map', []))
        except Exception:
            return 0

        if pkg is None:
            return 0

        resolver = CLITaskResolver.from_package(pkg)

        task_name = getattr(args, 'task', None)
        flag = getattr(args, 'flag', None)
        if task_name and flag:
            candidates = self._value_completions(resolver, task_name, flag, prefix)
        elif task_name:
            candidates = self._flag_completions(resolver, task_name, prefix)
        else:
            candidates = resolver.completions(prefix)

        for c in candidates:
            print(c)

        return 0

    def _flag_completions(self, resolver, task_name, prefix):
        """The `--flags` a task exposes (params declared `cli:`).

        Completion must never be the thing that fails: an unresolvable task or a
        task that exposes nothing yields no candidates rather than an error.
        """
        from ..cli_args import resolve_task_cli
        from ..cli_task_resolver import TaskResolutionError

        try:
            task = resolver.resolve(task_name)
        except TaskResolutionError:
            return []

        candidates = []
        for arg in resolve_task_cli(task):
            if arg.hidden:
                continue
            candidates.append("--%s" % arg.name)
            if arg.short:
                candidates.append("-%s" % arg.short)
        return [c for c in candidates if c.startswith(prefix)]

    def _value_completions(self, resolver, task_name, flag, prefix):
        """The values a task flag accepts -- `--detail <TAB>` -> quiet normal full.

        Sourced from the parameter's declared value set, which is what makes
        declaring the set pay for itself at the prompt. Silent on anything
        unresolvable, like flag completion.
        """
        from ..cli_args import resolve_task_cli
        from ..cli_task_resolver import TaskResolutionError
        from ..task import collect_param_value_sets

        try:
            task = resolver.resolve(task_name)
        except TaskResolutionError:
            return []

        name = flag.lstrip('-')
        # The flag may be named differently from the parameter it sets
        # (`cli: {name: ...}`), so map back through the exposed args first.
        param = name
        for a in resolve_task_cli(task):
            if a.name == name or a.short == name:
                param = a.param
                break

        vs = collect_param_value_sets(task).get(param)
        if vs is None:
            return []

        return [str(v) for v in vs.values() if str(v).startswith(prefix)]
