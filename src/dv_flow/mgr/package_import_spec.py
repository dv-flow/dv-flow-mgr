#****************************************************************************
#* package_import_spec.py
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
import pydantic.dataclasses as dc
import json
from typing import Dict, Any

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
class PackageImportSpec(object):
    path : str = dc.Field(default=None, alias="from")
    alias : str = dc.Field(default=None, alias="as")
