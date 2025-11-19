import dataclasses as dc
import logging
import os
from typing import ClassVar, Optional
from .package import Package
from .package_provider_yaml import PackageProviderYaml

try:
    import tomllib as tomli  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli

@dc.dataclass
class PackageProviderToml(PackageProviderYaml):
    _log : ClassVar[logging.Logger] = logging.getLogger("PackageProviderToml")

    def _parse_file(self, file: str, is_root: bool):
        if not file.endswith(".toml"):
            return super()._parse_file(file, is_root)
        with open(file, "rb") as fp:
            data = tomli.load(fp)
        # Emulate YAML loader behavior: attach srcinfo to mappings in key scopes
        scopes = {"tasks", "types", "body", "package", "fragment"}

        def add_srcinfo(obj, scope_stack):
            if isinstance(obj, dict):
                if scope_stack and scope_stack[-1] in scopes:
                    obj.setdefault("srcinfo", {"file": file})
                for k, v in list(obj.items()):
                    scope_stack.append(k)
                    add_srcinfo(v, scope_stack)
                    scope_stack.pop()
            elif isinstance(obj, list):
                for v in obj:
                    add_srcinfo(v, scope_stack)
        add_srcinfo(data, [])
        return data
