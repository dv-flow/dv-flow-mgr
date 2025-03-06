
from dv_flow.mgr import Task, TaskDataResult

async def Message(runner, input) -> TaskDataResult:
        print("%s: %s" % (input.name, input.params.msg), flush=True)
        return TaskDataResult()
