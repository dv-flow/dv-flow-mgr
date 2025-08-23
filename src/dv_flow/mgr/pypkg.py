import dataclasses as dc

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

    @dc.dataclass
    class Params():
        pass

    pass