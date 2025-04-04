import pydantic.dataclasses as pdc
from pydantic import BaseModel

class NeedDef(BaseModel):
    task : str = pdc.Field(
        description="Name of the task to depend on")