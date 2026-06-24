#****************************************************************************
#* package_map_provider.py
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
import dataclasses as dc
import logging
import os
import yaml
from typing import ClassVar, Dict, List, Optional
from .package import Package
from .package_loader_p import PackageLoaderP
from .package_provider import PackageProvider
from .package_provider_yaml import PackageProviderYaml


@dc.dataclass
class PackageMapProvider(PackageProvider):
    """Provider backed by a generated ``flow-packages.yaml`` map.

    The map is a pure ``name -> flow file`` directory (typically produced by an
    ivpm handler). Reading it registers package names without parsing any
    dependency; a dependency's ``flow.*`` is parsed only when ``findPackage``
    reaches it (lazy, exactly like ``ExtRgy``).
    """
    path : str
    _map : Optional[Dict[str, str]] = None          # name -> abs flow file (lazy)
    _provider_m : Dict[str, PackageProviderYaml] = dc.field(default_factory=dict)
    _log : ClassVar = logging.getLogger("PackageMapProvider")

    def _ensure_loaded(self, loader : Optional[PackageLoaderP]=None):
        if self._map is not None:
            return
        self._map = {}
        if not os.path.isfile(self.path):
            self._error(loader, "Package-map file %s not found" % self.path)
            return
        with open(self.path) as fp:
            doc = yaml.safe_load(fp) or {}
        root = doc.get("package-map")
        if root is None:
            self._error(loader, "'%s' is missing top-level 'package-map'" % self.path)
            return
        base = os.path.dirname(os.path.abspath(self.path))
        for e in root.get("packages", []):
            nm = e.get("name")
            p = e.get("path")
            if nm is None or p is None:
                self._error(loader,
                    "package-map entry in %s requires 'name' and 'path'" % self.path)
                continue
            abs_p = os.path.normpath(os.path.join(base, p))
            if nm in self._map:
                self._error(loader,
                    "Duplicate package '%s' in map %s; keeping first (%s)" % (
                        nm, self.path, self._map[nm]),
                    is_error=False)
                continue
            self._map[nm] = abs_p

    def _error(self, loader, msg, is_error=True):
        if loader is not None and hasattr(loader, "error"):
            loader.error(msg)
        else:
            self._log.warning(msg)

    def hasPackage(self, name : str, loader : Optional[PackageLoaderP]=None) -> bool:
        """Cheap membership check -- reads the map, never parses a dependency."""
        self._ensure_loaded(loader)
        return name in self._map

    def getPackageNames(self, loader : PackageLoaderP) -> List[str]:
        self._ensure_loaded(loader)
        return list(self._map.keys())

    def getPackage(self, name : str, loader : PackageLoaderP) -> Package:
        pkg = self.findPackage(name, loader)
        if pkg is None:
            raise Exception("Package %s not present in map %s" % (name, self.path))
        return pkg

    def findPackage(self, name : str, loader : PackageLoaderP) -> Optional[Package]:
        self._ensure_loaded(loader)
        if name not in self._map:
            return None
        if name not in self._provider_m:
            self._provider_m[name] = PackageProviderYaml(path=self._map[name])
        return self._provider_m[name].findPackage(name, loader)
