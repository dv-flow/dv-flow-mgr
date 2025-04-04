
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from typing import List, Union
from .param_def import ParamDef

class ExtendDef(BaseModel):
    """Extension definition"""
    task : str = pdc.Field(
        description="Name of the task to extend")
    params : List[ParamDef] = pdc.Field(
        default_factory=list,
        description="Parameter extensions to apply to the task",
        alias="with")
    uses : str = pdc.Field(
        default=None,
        description="Name of the extension to use as a base")
    needs: List[str] = pdc.Field(
        default_factory=list,
        description="List of tasks to depend on")

