from pydantic import BaseModel, Field
from typing import Any, List

class TaskOutput(BaseModel):
    type : str
    params : List[Any] = Field(default_factory=list, alias="with")