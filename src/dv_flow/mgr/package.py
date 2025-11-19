#****************************************************************************
#* package.py
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
import dataclasses as dc
import logging
from typing import Any, ClassVar, Dict, List, Union
from .fragment_def import FragmentDef
from .package_def import PackageDef
from .srcinfo import SrcInfo
from .task import Task
from .type import Type

@dc.dataclass
class Override(object):
    target : Union[str, 'Package']
    override : Union[str, 'Package']

@dc.dataclass
class Package(object):
    name : str = "<unknown>"
    basedir : str = None
    paramT : Any = None
    pkg_def : PackageDef = None  # Added to expose original PackageDef for tests
    # Package holds constructors for tasks
    # - Dict holds the default parameters for the task
    task_m : Dict[str,Task] = dc.field(default_factory=dict)
    type_m : Dict[str,Type] = dc.field(default_factory=dict)
    fragment_def_l : List[FragmentDef] = dc.field(default_factory=list)
    pkg_m : Dict[str, 'Package'] = dc.field(default_factory=dict)
#    overrides : Dict[str, str]
    srcinfo : SrcInfo = None
    _log : ClassVar = logging.getLogger("Package")

    def getTaskCtor(self, name : str) -> Task:
        self._log.debug("-- %s::getTaskCtor: %s" % (self.name, name))
        if name not in self.tasks.keys():
            raise Exception("Task %s not present in package %s" % (name, self.name))
        return self.tasks[name]
    
    def dump(self):
        tasks = {}
        types = {}
        for k, v in self.task_m.items():
            tasks[k] = v.dump()
        for k, v in self.type_m.items():
            types[k] = v.dump()

        pkg = {
            "name": self.name,
            "basedir": self.basedir,
            "tasks": tasks,
            "types": types,
            "fragments": [f.dump() for f in self.fragment_def_l]
        }

        if self.paramT is not None:
            pkg["paramT"] = self.paramT().model_dump()

        return pkg
            
    def __hash__(self):
        return id(self)
    
    def to_json(self, markers=None) -> dict:
        """Convert package data to a JSON-compatible dictionary format.
        
        Args:
            markers: Optional list of marker objects, each with 'msg' and 'severity' attributes
        
        Returns:
            dict: Dictionary containing required package data and markers
        """
        # Collect all imported packages recursively
        imports = {}
        files = []
        def collect_imports(pkg):
            nonlocal imports, files
            for name, p in pkg.pkg_m.items():
                if name not in imports.keys():
#                    imports[name] = (p.srcinfo.file + ":" + p.srcinfo.lineno)
                    if p.srcinfo is not None and p.srcinfo.file is not None:
                        imports[name] = "%s:%d" % (p.srcinfo.file, p.srcinfo.lineno)

#                    imports[name] = p.srcinfo.file
                    collect_imports(p)
                    if p.srcinfo.file not in files:
                        files.append(p.srcinfo.file)
        collect_imports(self)
        
        # Get files from fragments
        for frag in self.fragment_def_l:
            if frag.srcinfo and frag.srcinfo.file:
                files.append(frag.srcinfo.file)

        def format_srcinfo(srcinfo):
            if srcinfo:
                ret = srcinfo.file
                if srcinfo.lineno != -1:
                    ret += ":" + str(srcinfo.lineno)
                if srcinfo.linepos != -1:
                    ret += ":" + str(srcinfo.linepos)
                return ret
            return None
        result = {
            "name": self.name,
            "file": self.srcinfo.file if self.srcinfo else None,
            "imports": imports,
            "files": files,
            "markers": [],
            "tasks": [
                {
                    "name": name,
                    "srcinfo": format_srcinfo(task.srcinfo)
                }
                for name, task in self.task_m.items()
            ]
        }
        
        if markers:
            result["markers"] = [
                {"msg": marker.msg, "severity": str(marker.severity)}
                for marker in markers
            ]
            
        return result
