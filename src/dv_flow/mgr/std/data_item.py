from ..task_data import TaskDataInput, TaskDataResult
from ..task_run_ctxt import TaskRunCtxt

async def DataItem(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    status = 0
    output = []

    item = ctxt.mkDataItem(type=input.type, **getattr(input.params, "with"))

    return TaskDataResult(
        status=status,
        output=output
    )

