
from pydantic import BaseModel
import pydantic.dataclasses as pdc

class SrcInfo(BaseModel):
    file    : str = pdc.Field(default=None)
    lineno  : int = pdc.Field(default=-1)
    linepos : int = pdc.Field(default=-1)

    def dump(self):
        return {
            "file": self.file,
            "line": self.lineno,
            "pos": self.linepos
        }
