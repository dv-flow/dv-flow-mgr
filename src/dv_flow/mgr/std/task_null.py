from pydantic import BaseModel
from ..task_data import TaskDataResult

class TaskNullParams(BaseModel):
    pass

async def TaskNull(runner, input) -> TaskDataResult:
    return TaskDataResult()

