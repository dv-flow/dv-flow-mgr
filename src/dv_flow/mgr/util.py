#****************************************************************************
#* util.py
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
import yaml
from .package_def import PackageDef

def loadProjPkgDef(path):
    """Locates the project's flow spec and returns the PackageDef"""

    dir = path
    ret = None
    while dir != "/" and dir != "" and os.path.isdir(dir):
        if os.path.exists(os.path.join(dir, "flow.dv")):
            with open(os.path.join(dir, "flow.dv")) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                if "package" in data.keys():
                    ret = PackageDef.load(os.path.join(dir, "flow.dv"))
                    break
        dir = os.path.dirname(dir)
    return ret

