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

        print("params: %s" % str(params))
        return params
