from pydantic import BaseModel, Field
from typing import Any, Dict, List

class TaskOutput(BaseModel):
    type : str
    params : List[Any] = Field(default_factory=list, alias="with")
    deps : Dict[str,List[str]] = Field(default_factory=dict)