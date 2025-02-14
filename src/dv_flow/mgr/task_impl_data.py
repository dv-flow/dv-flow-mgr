
from pydantic import BaseModel
from typing import Any, ClassVar, Dict, Set, List, Tuple

class TaskImplParams(BaseModel):
    pass

class TaskImplSourceData(BaseModel):
    params : Any
    changed : bool
    memento : Any

class TaskImplResultData(BaseModel):
    data : List[Any]
    changed : bool
    memento : Any

