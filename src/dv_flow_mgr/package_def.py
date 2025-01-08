#****************************************************************************
#* package_def.py
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
from .package import Package
from .task import TaskParamCtor
from .task_def import TaskDef, TaskSpec

@dc.dataclass
class PackageSpec(object):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    _fullname : str = None

    def get_fullname(self) -> str:
        if self._fullname is None:
            if len(self.params) != 0:
                self._fullname = "%s%s}" % (
                    self.name,
                    json.dumps(self.params, separators=(',', ':')))
            else:
                self._fullname = self.name
        return self._fullname    
    
    def __hash__(self):
        return hash(self.get_fullname())

    def __eq__(self, value):
        return isinstance(value, PackageSpec) and value.get_fullname() == self.get_fullname()

@dc.dataclass
class PackageImportSpec(PackageSpec):
    path : str = dc.Field(default=None, alias="from")
    alias : str = dc.Field(default=None, alias="as")

class PackageDef(BaseModel):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    type : List[PackageSpec] = dc.Field(default_factory=list)
    tasks : List[TaskDef] = dc.Field(default_factory=list)
    imports : List[PackageImportSpec] = dc.Field(default_factory=list)
    fragments: List[str] = dc.Field(default_factory=list)

#    import_m : Dict['PackageSpec','Package'] = dc.Field(default_factory=dict)

    basedir : str = None

    def getTask(self, name : str) -> 'TaskDef':
        for t in self.tasks:
            if t.name == name:
                return t
    
    def mkPackage(self, session, params : Dict[str,Any] = None) -> 'Package':
        ret = Package(self.name)

        for task in self.tasks:
            if task.type is not None:
                # Find package (not package_def) that implements this task
                # Insert an indirect reference to that tasks's constructor

                # Only call getTaskCtor if the task is in a different package
                task_t = task.type if isinstance(task.type, TaskSpec) else TaskSpec(task.type)
                ctor_t = session.getTaskCtor(task_t, self)

                ctor_t = TaskParamCtor(
                    base=ctor_t, 
                    params=task.params, 
                    basedir=self.basedir,
                    depend_refs=task.depends)
            else:
                raise Exception("")
            ret.tasks[task.name] = ctor_t

        return ret

