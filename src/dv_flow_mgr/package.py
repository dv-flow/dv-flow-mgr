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
from typing import Any, Dict, List
from .flow import Flow
from .task import Task

@dc.dataclass
class PackageSpec(object):
    name : str
    params : Dict[str,Any] = dc.field(default_factory=dict)
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
class Package(object):
    name : str
    params : Dict[str,Any] = dc.field(default_factory=dict)
    type : List[PackageSpec] = dc.field(default_factory=list)
    tasks : Dict[str,Task] = dc.field(default_factory=dict)

    @staticmethod
    def mk(self, doc, filename) -> 'Package':
        if "package" not in doc.keys():
            raise Exception("Missing 'package' key in %s" % filename)
        pkg_e = doc["package"]

        if "name" not in pkg_e.keys():
            raise Exception("Missing package 'name' key in %s" % filename)
        
        pkg = Package(pkg_e["name"])

        if "type" not in pkg_e.keys():
            raise Exception("Missing package 'type' key in %s" % filename)
        
        # Type could either by just a value or a list of values
        if isinstance(pkg_e["type"], str):
            pkg.type.append(PackageSpec(pkg_e["type"]))
        else:
            for t in pkg_e["type"]:
                pkg.type.append(PackageSpec(t))
        
        if "tasks" in pkg_e.keys():
            for t in pkg_e["tasks"]:
                task = Task.mk(t, filename)
                if task.name in pkg.tasks.keys():
                    raise Exception("Duplicate task %s in %s" % (task.name, filename))
                pkg.tasks[task.name] = task

        return pkg


    def elab(self, session):
        # TODO: determine which tasks stay, and what (if any)
        # changes are made in them
        # - Ensure we have bases
        # - Populate the tasks lists bottom-up, linking sub->super
        pass


