
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from typing import List, Union, Any
from .extend_def import ExtendDef
from .param_def import ParamDef

class OverrideDef(BaseModel):
    """Override definition"""
    package : Union[str, None] = pdc.Field(
        description="Package to override")
    task : Union[str, None] = pdc.Field(
        description="Task to override")
    value : str = pdc.Field(
        description="Override to use",
        alias="with")

class ConfigDef(BaseModel):
    name : str = pdc.Field(
        description="Name of the configuration")
    params : List[ParamDef] = pdc.Field(
        default_factory=list,
        description="List of configuration parameters",
        alias="with")
    uses : str = pdc.Field(
        default=None,
        description="Name of the configuration to use as a base")
    overrides : List[OverrideDef] = pdc.Field(
        default_factory=list,
        description="List of package and task overrides")
    extensions : List[ExtendDef] = pdc.Field(
        default_factory=list,
        description="List of extensions to apply")
