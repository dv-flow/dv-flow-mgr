
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from typing import Dict, List, Union

class ExtendDef(BaseModel):
    """Extension definition"""
    task : str = pdc.Field(
        description="Name of the task to extend")
    params : Dict[str, Union[str, list, int, bool, dict]] = pdc.Field(
        default_factory=dict,
        description="Parameter modifications to apply to the task",
        alias="with")
    uses : str = pdc.Field(
        default=None,
        description="Name of the extension to use as a base")
    needs: List[str] = pdc.Field(
        default_factory=list,
        description="Additional task dependencies to inject")
