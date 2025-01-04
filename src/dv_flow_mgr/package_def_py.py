#****************************************************************************
#* package_def_py.py
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
import pydantic.dataclasses as dc
import json
from pydantic import BaseModel
from typing import Any, Dict, List
from .flow import Flow
from .package_def import PackageDef
from .package import Package
from .task_def import TaskDef
from .task_template import TaskTemplate

class PackageDefPy(PackageDef):

    def mkPackage(self, session, params : Dict[str,Any] = None) -> 'PackageDef':
        ret = Package(self.name)

        for task in self.tasks:
            ret.tasks.append(task.copy())
            ret.tasks.append(t.copy())
        ret = self.model_copy()
        ret.params = params

        # TODO: 

        return ret

