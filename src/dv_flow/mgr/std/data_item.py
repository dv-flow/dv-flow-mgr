from ..task_data import TaskDataInput, TaskDataResult
from ..task_run_ctxt import TaskRunCtxt

async def DataItem(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    status = 0
    output = []

    print("DataItem: %s" % input.params)

    with_c = getattr(input.params, "with")
    item = ctxt.mkDataItem(type=input.params.type, **with_c)

    return TaskDataResult(
        status=status,
        output=output
    )

