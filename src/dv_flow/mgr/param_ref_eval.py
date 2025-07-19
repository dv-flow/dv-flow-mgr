#****************************************************************************
#* param_ref_eval.py
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
import json
from .expr_eval import ExprEval
from .expr_parser import ExprParser
from .eval_jq import eval_jq

@dc.dataclass
class ParamRefEval(object):

    parser : ExprParser = dc.field(default_factory=ExprParser)
    expr_eval : ExprEval = dc.field(default_factory=ExprEval)

    def __post_init__(self):
        self.expr_eval.methods["jq"] = eval_jq

    def set(self, name : str, value : object):
        self.expr_eval.set(name, value)

    def set_name_resolution(self, ctx: 'NameResolutionContext'):
        self.expr_eval.set_name_resolution(ctx)

    def eval(self, val : str) -> str:
        idx = 0

        while True:
            idx = val.find("${{", idx)

            if idx != -1:
                eidx = val.find("}}", idx+1)

                if eidx == -1:
                    raise Exception("unterminated variable ref")
                
                ref = val[idx+3:eidx].strip()

#                expr_ast = self.parser.parse(ref)
                exp_val = self.expr_eval.eval(ref)

                # Replacing [idx..eidx+2] with len(exp_val)
                val = val[:idx] + exp_val + val[eidx+2:]
                idx += len(exp_val)
            else:
                break

        return val
    
    def setVar(self, name, value):
        self.expr_eval.variables[name] = value
