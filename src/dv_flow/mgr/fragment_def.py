#****************************************************************************
#* fragment_def.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
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
import pydantic.dataclasses as dc
import json
from pydantic import BaseModel
from typing import Any, Dict, List, Union
from .package_import_spec import PackageImportSpec
from .srcinfo import SrcInfo
from .task_def import TaskDef
from .type_def import TypeDef

class FragmentDef(BaseModel):
    tasks : List[TaskDef] = dc.Field(default_factory=list)
    imports : List[Union[str,PackageImportSpec]] = dc.Field(default_factory=list, alias="imports")
    fragments: List[str] = dc.Field(default_factory=list)
    types : List[TypeDef] = dc.Field(default_factory=list)
    srcinfo : SrcInfo = dc.Field(default=None)

    _basedir : str = None

    def getTask(self, name : str) -> 'TaskDef':
        for t in self.tasks:
            if t.name == name:
                return t
            
#    def apply(self, session, pkg : Package):
#        pass
            
