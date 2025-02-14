
from typing import List, Union
from pydantic import BaseModel, Field
from .param_def import ParamDef

class TypeDef(BaseModel):
    name : str
    uses : str = None
    doc : str = None
    fields : List[ParamDef] = Field(alias="with", default_factory=list)
