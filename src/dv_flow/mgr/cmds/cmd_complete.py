"""
Tab-completion helper for shells (bash, zsh, fish).

Usage from a shell completion function::

    dfm complete <prefix>

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
                config=getattr(args, 'config', None))
        except Exception:
            return 0

        if pkg is None:
            return 0

        resolver = CLITaskResolver.from_package(pkg)
        candidates = resolver.completions(prefix)

        for c in candidates:
            print(c)

        return 0
