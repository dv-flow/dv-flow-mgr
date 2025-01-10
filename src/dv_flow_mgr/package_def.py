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
from .fragment_def import FragmentDef
from .package import Package
from .package_import_spec import PackageImportSpec, PackageSpec
from .task import TaskParamCtor
from .task_def import TaskDef, TaskSpec


class PackageDef(BaseModel):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    type : List[PackageSpec] = dc.Field(default_factory=list)
    tasks : List[TaskDef] = dc.Field(default_factory=list)
    imports : List[PackageImportSpec] = dc.Field(default_factory=list)
    fragments: List[str] = dc.Field(default_factory=list)

    fragment_l : List['FragmentDef'] = dc.Field(default_factory=list, exclude=True)

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
                # We use the Null task from the std package
                raise Exception("")
            ret.tasks[task.name] = ctor_t

        for frag in self.fragment_l:
            for task in frag.tasks:
                if task.type is not None:
                    # Find package (not package_def) that implements this task
                    # Insert an indirect reference to that tasks's constructor

                    # Only call getTaskCtor if the task is in a different package
                    task_t = task.type if isinstance(task.type, TaskSpec) else TaskSpec(task.type)
                    ctor_t = session.getTaskCtor(task_t, self)

                    ctor_t = TaskParamCtor(
                        base=ctor_t, 
                        params=task.params, 
                        basedir=frag.basedir,
                        depend_refs=task.depends)
                else:
                    # We use the Null task from the std package
                    raise Exception("")
                if task.name in ret.tasks:
                    raise Exception("Task %s already defined" % task.name)
                ret.tasks[task.name] = ctor_t

        return ret

