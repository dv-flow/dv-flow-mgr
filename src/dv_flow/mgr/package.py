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
import logging
from typing import Any, ClassVar, Dict
from .task_ctor import TaskCtor

@dc.dataclass
class Package(object):
    name : str
    params : Dict[str,Any] = dc.field(default_factory=dict)
    # Package holds constructors for tasks
    # - Dict holds the default parameters for the task
    tasks : Dict[str,TaskCtor] = dc.field(default_factory=dict)
    types : Dict[str,Any] = dc.field(default_factory=dict)
    _log : ClassVar = logging.getLogger("Package")

    def getTaskCtor(self, name : str) -> TaskCtor:
        self._log.debug("-- %s::getTaskCtor: %s" % (self.name, name))
        if name not in self.tasks.keys():
            raise Exception("Task %s not present in package %s" % (name, self.name))
        return self.tasks[name]
            
    def __hash__(self):
        return hash(self.fullname())

