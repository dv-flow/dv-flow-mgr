import dataclasses as dc
from typing import ClassVar, Dict

# dv_flow.mgr as dfm
# dfm.PyPkg
# A sort of package factory

@dc.dataclass
class PyPkg(object):
    # Desc:
    # Uses: _uses_ : Package class or identifier
    # Params:
    # Tasks: search local by default
    # - Rely on simple names for override?
    # Types: search local by default
    #
    # Package should be able to determine what 'uses' it
    # Package factory handles overrides by inheritance?
    _tasks : Dict = dc.field(default_factory=dict)
    _pkg_rgy : ClassVar[Dict] = {}

    @dc.dataclass
    class Params(object): pass

    @classmethod
    def registerTask(cls, T):
        if cls in cls._pkg_rgy.keys():
            pkg = cls._pkg_rgy[cls]
        else:
            pkg = cls()
            cls._pkg_rgy[cls] = pkg

        name = getattr(cls, "name", T.__name__)
        print("Package: %s" % name)
        print("registerTask: %d (%s)" % (len(pkg._tasks), str(cls)))
        pkg._tasks[T.__name__] = T

        print("Params: %s" % T.Params)
        print("%d " % T.Params.a)

    pass

def pypkg(T):
    return T
