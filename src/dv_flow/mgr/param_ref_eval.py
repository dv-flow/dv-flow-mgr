import dataclasses as dc
import json
from .expr_eval import ExprEval
from .expr_parser import ExprParser
from .eval_jq import eval_jq

@dc.dataclass
class ParamRefEval(object):

    parser : ExprParser = ExprParser()
    expr_eval : ExprEval = ExprEval()

    def __post_init__(self):
        self.expr_eval.methods["jq"] = eval_jq

    def eval(self, val : str) -> str:
        idx = 0

        while True:
            idx = val.find("${{", idx)

            if idx != -1:
                eidx = val.find("}}", idx+1)

                if eidx == -1:
                    raise Exception("unterminated variable ref")
                
                ref = val[idx+3:eidx].strip()
                print("ref: %s" % ref)

                expr_ast = self.parser.parse(ref)
                print("expr_ast: %s" % str(expr_ast))
                exp_val = self.expr_eval.eval(expr_ast)
                print("exp_val: %s" % str(exp_val))

                # Replacing [idx..eidx+2] with len(exp_val)
                val = val[:idx] + exp_val + val[eidx+2:]
                idx += len(exp_val)



            else:
                break

        return val
    
    def setVar(self, name, value):
        self.expr_eval.variables[name] = value
