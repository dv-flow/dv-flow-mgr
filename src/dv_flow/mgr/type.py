import dataclasses as dc
from typing import Any, Dict, List, TYPE_CHECKING
from .srcinfo import SrcInfo

if TYPE_CHECKING:
    from .param_def_collection import ParamDefCollection

@dc.dataclass
class TypeField(object):
    name : str
    type : Any
    doc : str = None
    value : str = None
    append : List[Any] = None
    srcinfo : SrcInfo = None

@dc.dataclass
class Type(object):
    name : str
    doc : str = None
    params : Dict[str, TypeField] = dc.field(default_factory=dict)
    paramT : Any = None
    param_defs : 'ParamDefCollection' = None
    uses : 'Type' = None
    tags : List[Any] = dc.field(default_factory=list)
    srcinfo : SrcInfo = None
    typedef : 'TypeDef' = None

    def dump(self):
        ret = {}
        ret["name"] = self.name
        ret["doc"] = self.doc
        ret["params"] = {}
        ret['srcinfo'] = self.srcinfo.dump()

        return ret
    
    def __hash__(self):
        return id(self)
