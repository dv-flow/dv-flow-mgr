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
import dataclasses as dc
from typing import Any, Dict, List, Tuple


@dc.dataclass
class Task(object):
    name : str
    override : bool = False
    type : List[Tuple[str,'Task']] = dc.field(default_factory=list)
    depends : List[Tuple[str,'Task']] = dc.field(default_factory=list)
    args : Dict[str,Any] = dc.field(default_factory=dict)

    @staticmethod 
    def mk(doc, filename) -> 'Task':
        task = None
        if "name" in doc.keys():
            task = Task(doc["name"])
            if "type" in doc.keys():
                for t in doc["type"]:
                    task.type.append((t, None))
        elif "override" in doc.keys():
            task = Task(doc["override"], override=True)
            if "type" in doc.keys():
                raise Exception("Task 'override' cannot have a 'type' key in %s" % filename)
        else:
            raise Exception("Missing task 'name' or 'override' key in %s" % filename)
        
        if "depends" in doc.keys():
            for d in doc["depends"]:
                task.depends.append((d, None))
        
        if "args" in doc.keys():
            task.args = doc["args"].copy()
        
        return task
    
    def elab(self, session):
        # 
        pass


