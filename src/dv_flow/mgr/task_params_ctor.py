#****************************************************************************
#* task_params_ctor.py
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
from typing import Any, List


@dc.dataclass
class TaskParamsCtor(object):

    paramT : Any = None
    # List of parameter-setting sets, starting with inner-most
    values : List[Any] = dc.field(default_factory=list)

    def mk(self, input) -> Any:
        params = self.paramT()

        # Now, process each field 
        for field in dc.fields(self.paramT):
            # Find the outer-most setting of the value
            last_value_i = -1
            for i in range(len(self.values)-1, -1, -1):
                if hasattr(self.values[i], field.name) and getattr(self.values[i], field.name) is not None:
                    val = getattr(self.values[i], field.name)
                    # TODO: check if 'val' is a set or mutator
                    last_value_i = i
                    break
            for i in range(last_value_i, -1, -1):
                if hasattr(self.values[i], field.name):
                    val = getattr(self.values[i], field.name)
                    setattr(params, field.name, val)

        return params
