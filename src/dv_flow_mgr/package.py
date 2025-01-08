#****************************************************************************
#* package.py
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
import dataclasses as dc
import json
from pydantic import BaseModel
from typing import Any, Callable, Dict, List, Tuple
from .flow import Flow
from .task import TaskParams, TaskCtor
from .task_def import TaskDef

class PackageAcc(object):
    pkg_spec : 'PackageSpec'
    session : 'Session'
    pkg : 'Package' = None

    def getPackage(self) -> 'Package':
        if self.pkg is None:
            self.pkg = self.session.getPackage(self.pkg_spec)
        return self.pkg

@dc.dataclass
class Package(object):
    name : str
    params : Dict[str,Any] = dc.field(default_factory=dict)
    # Package holds constructors for tasks
    # - Dict holds the default parameters for the task
    tasks : Dict[str,TaskCtor] = dc.field(default_factory=dict)
    imports : List['PackageAcc'] = dc.field(default_factory=list)

    def getPackage(self, name : str) -> 'Package':
        for p in self.imports:
            if p.name == name:
                return p.getPackage()
            
    def getTaskCtor(self, name : str) -> TaskCtor:
        return self.tasks[name]
            
    def mkTaskParams(self, name : str) -> TaskParams:
        if name not in self.tasks:
            raise Exception("Task " + name + " not found")
        return self.tasks[name].mkTaskParams()
    
    def setTaskParams(self, name : str, params : TaskParams, pvals : Dict[str,Any]):
        if name not in self.tasks:
            raise Exception("Task " + name + " not found")
        self.tasks[name].setTaskParams(params, pvals)

    def mkTask(self, 
               name : str, 
               task_id : int, 
               session : 'Session',
               params : TaskParams,
               depends : List['Task']) -> 'Task':
        # TODO: combine parameters to create the full taskname
        task =  self.tasks[name].mkTask(name, task_id, session, params, depends)
        return task

    def __hash__(self):
        return hash(self.fullname())

