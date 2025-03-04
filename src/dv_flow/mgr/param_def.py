
from typing import Any, List, Union
from pydantic import BaseModel, Field

class ListType(BaseModel):
    item : Union[str, 'ComplexType']

class MapType(BaseModel):
    key : Union[str, 'ComplexType']
    item : Union[str, 'ComplexType']

class ComplexType(BaseModel):
    list : Union[ListType, None] = None
    map : Union[MapType, None] = None

class ParamDef(BaseModel):
    doc : str = None
    type : Union[str, 'ComplexType'] = None
    value : Union[Any, None] = None
    append : Union[Any, None] = None
    prepend : Union[Any, None] = None
    path_append : Union[Any, None] = Field(alias="path-append", default=None)
    path_prepend : Union[Any, None] = Field(alias="path-prepend", default=None)

