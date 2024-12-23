#****************************************************************************
#* session.py
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
import os
import copy
import yaml
import dataclasses as dc
from typing import Any, Dict, List
from .package import Package, PackageSpec

@dc.dataclass
class Session(object):
    """Manages the running of a flow"""

    # Search path for .flow files
    package_path : List[str] = dc.field(default_factory=list)
    package_map : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    package : Package = None
    _root_dir : str = None

    def load(self, root : str):
        if os.path.isdir(root):
            root_f = []
            for f in os.listdir(root):
                if f.endswith(".flow"):
                    root_f.append(os.path.join(root, f))
            if len(root_f) == 0:
                raise Exception("No .flow files found in " + root)
            elif len(root_f) > 1:
                raise Exception("Multiple .flow files found in " + root + "(" + ",".join(root_f) + ")")
            else:
                root = root_f[0]

        self._root_dir = os.path.dirname(root)

        self.package = self._load_package(root, [])

    def _load_package(self, root : str, file_s : List[str]) -> Package:
        if root in file_s:
            raise Exception("Recursive file processing @ %s: %s" % (root, ",".join(self._file_s)))
        file_s.append(root)
        ret = None
        with open(root, "r") as fp:
            doc = yaml.load(fp, Loader=yaml.FullLoader)
            ret = Package.mk(doc, root)
        file_s.pop()

    def getPackage(self, spec : PackageSpec) -> Package:
        if spec in self.package_map.keys():
            return self.package_map[spec]
        else:
            base_spec = PackageSpec(spec.name)
            if not base_spec in self.package_map.keys():
                # Template is not present. Go find it...

                # If not found...
                raise Exception("Package not found")

            base = self.package_map[PackageSpec(spec.name)]
            base_c = copy.deepcopy(base)
            base_c.params.update(spec.params)
            base_c.elab(self)
            self.package_map[spec] = base_c
            return base_c

