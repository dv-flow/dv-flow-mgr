
import pydantic.dataclasses as dc
import json
from typing import Dict, Any

@dc.dataclass
class PackageSpec(object):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    _fullname : str = None

    def get_fullname(self) -> str:
        if self._fullname is None:
            if len(self.params) != 0:
                self._fullname = "%s%s}" % (
                    self.name,
                    json.dumps(self.params, separators=(',', ':')))
            else:
                self._fullname = self.name
        return self._fullname    
    
    def __hash__(self):
        return hash(self.get_fullname())

    def __eq__(self, value):
        return isinstance(value, PackageSpec) and value.get_fullname() == self.get_fullname()

@dc.dataclass
class PackageImportSpec(PackageSpec):
    path : str = dc.Field(default=None, alias="from")
    alias : str = dc.Field(default=None, alias="as")