
import dataclasses as dc
from typing import Any, List

@dc.dataclass
class Config(object):
    overrides : List
    paramT : Any = None
