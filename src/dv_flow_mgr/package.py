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
from .task_def import TaskDef

class PackageAcc(object):
    pkg_spec : 'PackageSpec'
    session : 'Session'
    pkg : 'Package' = None

    def getPackage(self) -> 'Package':
        if self.pkg is None:
            self.pkg = self.session.getPackage(self.pkg_spec)
        return self.pkg

class TaskCtor(object):
    def mkTaskParams(self, params : Dict) -> Dict:
        raise NotImplementedError()
    def mkTask(self, name : str, task_id : int, session : 'Session', params : Dict, depends : List['Task']) -> 'Task':
        raise NotImplementedError()         
    
class TaskParamCtor(object):
    base : TaskCtor
    params : Dict[str,Any]

    def mkTaskParams(self, params : Dict) -> Dict:
        # First, apply the task-specific parameters
        params_p = self.base.mkTaskParams(self.params)

        # Then, apply the parameters passed in
        # TODO:

        return params_p

    def mkTask(self, name : str, task_id : int, session : 'Session', params : Dict, depends : List['Task']) -> 'Task':
        return self.base.mkTask(name, task_id, session, params, depends)

@dc.dataclass
class PackageTaskCtor(TaskCtor):
    name : str
    pkg : 'Package'

    def mkTaskParams(self, params : Dict) -> Dict:
        return self.pkg.mkTaskParams(self.name, params)
    def mkTask(self, name : str, task_id : int, session : 'Session', params : Dict, depends : List['Task']) -> 'Task':
        return self.pkg.mkTask(self.name, task_id, session, params, depends)


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
            
    def mkTaskParams(self, name : str, params : Dict) -> Dict:
        ret = dict(self.params)
        if name in self.tasks:
            ret.update(self.tasks[name][0])
        ret.update(params)
        return ret
            
    def mkTask(self, 
               name : str, 
               task_id : int, 
               session : 'Session',
               params : Dict,
               depends : List['Task']) -> 'Task':
        # TODO: combine parameters to create the full taskname
        return self.tasks[name].mkTask(name, task_id, session, params, depends)

    def __hash__(self):
        return hash(self.fullname())

