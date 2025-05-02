import dataclasses as dc
from typing import Any
from .task_data import TaskDataResult, TaskDataInput
from .task_run_ctxt import TaskRunCtxt

@dc.dataclass
class DataCallable(object):
    paramT : Any

    async def __call__(self, ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
        output = []
        status = 0

        data = self.paramT()

        # Now, copy in the parameter values
        for key in self.paramT.model_fields.keys():
            if hasattr(input.params, key):
                setattr(data, key, getattr(input.params, key))

        output.append(data)

        return TaskDataResult(
            status=status,
            output=output
        )