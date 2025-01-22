#****************************************************************************
#* flow.py
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
from pydantic import BaseModel, Field
from typing import ClassVar
#from .task import Task

class Flow(BaseModel):
    # - Parameters are user-facing 
    # - Any implementation data must be stored elsewhere, such that it isn't
    #   checked for equality...
    name : str
    description : str = Field(None)


    @classmethod
    def mk(cls, *args, **kwargs):
        pass

    async def my_method(self):
        return Task(a,b,c)(self, input)

#@extend(target)
#class FlowExt(object):
#    pass


class Flow2(Flow):
    description : str = "abc"

    async def my_method(self):
        super().my_method()

f = Flow2(name="foo")

#for d in dir(f):
#    if not d.startswith("_"):
#        print("%s: %s" % (d, str(getattr(f, d))))



