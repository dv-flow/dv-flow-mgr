"""P0 groundwork tests: PackageProvider contract + dual-key loader cache."""
import os
from typing import List, Optional

from dv_flow.mgr.package import Package
from dv_flow.mgr.package_loader import PackageLoader
from dv_flow.mgr.package_provider import PackageProvider
from dv_flow.mgr.srcinfo import SrcInfo


def test_cache_pkg_dual_key(tmpdir):
    """_cache_pkg records a package under its given name, its own name, and abs path."""
    loader = PackageLoader()
    f = os.path.join(str(tmpdir), "flow.dv")
    pkg = Package(name="foo", srcinfo=SrcInfo(file=f))

    loader._cache_pkg(pkg, "alias")

    assert loader._pkg_m["alias"] is pkg            # given name
    assert loader._pkg_m["foo"] is pkg              # package's own name
    assert loader.findPackageByPath(f) is pkg       # abs-path cache
    # Path lookup must normalize
    assert loader.findPackageByPath(os.path.join(str(tmpdir), ".", "flow.dv")) is pkg


def test_getpackagenames_best_effort():
    """A provider may resolve by name while reporting no names from getPackageNames."""

    class SearchProvider(PackageProvider):
        def __init__(self):
            self.lookups = []

        def getPackageNames(self, loader) -> List[str]:
            return []  # search-style: can't enumerate

        def getPackage(self, name, loader) -> Package:
            return self.findPackage(name, loader)

        def findPackage(self, name, loader) -> Optional[Package]:
            self.lookups.append(name)
            if name == "needle":
                return Package(name="needle")
            return None

    loader = PackageLoader()
    sp = SearchProvider()
    loader._pkg_providers.insert(0, sp)

    # Enumeration sees nothing from this provider...
    assert "needle" not in sp.getPackageNames(loader)
    # ...but resolution is authoritative and gets cached.
    pkg = loader.findPackage("needle")
    assert pkg is not None and pkg.name == "needle"
    assert loader._pkg_m["needle"] is pkg
    # Second lookup is served from cache (provider not hit again).
    n_before = len(sp.lookups)
    loader.findPackage("needle")
    assert len(sp.lookups) == n_before
