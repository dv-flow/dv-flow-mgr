
import pydantic.dataclasses as pdc
from pydantic import BaseModel, model_validator
from typing import List, Union, Any
from .extend_def import ExtendDef
from .param_def import ParamDef

class OverrideDef(BaseModel):
    """Override definition for task or package substitution.
    
    Exactly one of 'task', 'package', or 'override' (deprecated) must be set.
    """
    task : Union[str, None] = pdc.Field(
        default=None,
        description="Fully-qualified name of task to override")
    package : Union[str, None] = pdc.Field(
        default=None,
        description="Name of package to override")
    override : Union[str, None] = pdc.Field(
        default=None,
        description="(Deprecated) Task or package to override")
    value : Union[str, dict] = pdc.Field(
        description="Replacement task name (str) or inline task definition (dict)",
        alias="with")

    @model_validator(mode='after')
    def validate_target(self):
        targets = [x for x in [self.task, self.package, self.override] if x is not None]
        if len(targets) == 0:
            raise ValueError("One of 'task', 'package', or 'override' must be set")
        if len(targets) > 1:
            raise ValueError("Only one of 'task', 'package', or 'override' can be set")
        return self

    @property
    def target_task(self) -> Union[str, None]:
        """Return the task target, handling legacy 'override' field."""
        return self.task or self.override

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
