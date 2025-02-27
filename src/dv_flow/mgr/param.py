
from pydantic import BaseModel
import pydantic.dataclasses as pdc
from typing import Any, List, Union

class ParamMeta(type):
    def __getitem__(self, T):
        ret = Union[T, Param]
        return ret

class ParamT(metaclass=ParamMeta):
    pass

class Param(BaseModel):
    append : Union[Any,List] = pdc.Field(default=None)
    prepend : Union[Any,List] = pdc.Field(default=None)
    append_path : Union[Any,List] = pdc.Field(default=None, alias="append-path")
    prepend_path : Union[Any,List] = pdc.Field(default=None, alias="prepend-path")


