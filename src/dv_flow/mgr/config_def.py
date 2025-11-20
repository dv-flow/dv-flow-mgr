
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from typing import List, Union, Any
from .extend_def import ExtendDef
from .param_def import ParamDef

class OverrideDef(BaseModel):
    """Override definition"""
    override : Union[str, None] = pdc.Field(
        description="Task or package to override")
    value : str = pdc.Field(
        description="Override to use",
        alias="with")

class ConfigDef(BaseModel):
    name : str = pdc.Field(
        description="Name of the configuration")
    params : List[ParamDef] = pdc.Field(
        default_factory=list,
        description="Configuration parameters map",
        alias="with")
    uses : str = pdc.Field(
        default=None,
        description="Name of the configuration to use as a base")
    overrides : List[OverrideDef] = pdc.Field(
        default_factory=list,
        description="List of package overrides")
    extensions : List[ExtendDef] = pdc.Field(
        default_factory=list,
        description="List of extensions to apply")
    imports : List[Union[str,'PackageImportSpec']] = pdc.Field(
        default_factory=list,
        description="List of packages to import for this config")
    fragments : List[str] = pdc.Field(
        default_factory=list,
        description="List of fragments to apply for this config")
    tasks : List['TaskDef'] = pdc.Field(
        default_factory=list,
        description="List of tasks defined/overridden by this config")
    types : List['TypeDef'] = pdc.Field(
        default_factory=list,
        description="List of types defined/overridden by this config")
