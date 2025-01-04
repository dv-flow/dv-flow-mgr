#****************************************************************************
#* task.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import asyncio
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Tuple

@dc.dataclass
class TaskSpec(object):
    name : str


class TaskTemplate(BaseModel):
    name : str

    # Implementation data below
    tmpl_basedir : str = dc.Field(default=None)
    impl : str = None
    body: Dict[str,Any] = dc.Field(default_factory=dict)
    impl_t : Any = None

    def getField(self, name : str) -> Any:
        if name in self.__dict__.keys():
            return self.__dict__[name]
        elif name in self.__pydantic_extra__.keys():
            return self.__pydantic_extra__[name]
        else:
            raise Exception("No such field %s" % name)
        



