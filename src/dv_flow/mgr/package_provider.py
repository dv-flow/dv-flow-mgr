import abc
from typing import List, Optional, Protocol, TYPE_CHECKING
from .package import Package

if TYPE_CHECKING:
    from .package_loader_p import PackageLoader

class PackageProvider(Protocol):
    """A source of packages.

    A provider answers two questions, with deliberately different guarantees:

    - ``findPackage`` is *authoritative*: given a package name it resolves and
      parses the package **on demand**, caches it, and returns ``None`` if it
      does not own that name. This is the single lazy entry point -- a package
      is parsed the first time some provider's ``findPackage`` reaches it, and
      never before.

    - ``getPackageNames`` is *best-effort* enumeration, used by "list/discover
      everything" paths. It is explicitly allowed to be incomplete -- and may
      be empty -- for search-style providers (e.g. ``DV_FLOW_PATH``) that can
      only answer "do you have *this* name?" without enumerating. Consumers must
      treat the result as best-effort and rely on ``findPackage`` for authority.
    """

    @abc.abstractmethod
    def getPackageNames(self, loader : 'PackageLoader') -> List[str]:
        """Best-effort list of package names this provider can resolve.

        May be incomplete or empty for search-style providers."""
        pass

    @abc.abstractmethod
    def getPackage(self, name : str, loader : 'PackageLoader') -> Package: pass

    @abc.abstractmethod
    def findPackage(self, name : str, loader : 'PackageLoader') -> Optional[Package]:
        """Resolve and parse *name* on demand; return ``None`` if not owned."""
        pass


