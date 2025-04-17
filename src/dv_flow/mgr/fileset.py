#****************************************************************************
#* fileset.py
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
from pydantic import BaseModel
from typing import Any, Dict, List, Tuple

class FileSet(BaseModel):
    type: str = "std.FileSet"
    filetype : str
    basedir : str
    name : str = ""
    src : str = None
    seq : int = -1
    files : List[str] = dc.Field(default_factory=list)
    incdirs: List[str] = dc.Field(default_factory=list)
    defines: List[str] = dc.Field(default_factory=list)
    params : Dict[str,str] = dc.Field(default_factory=dict)
