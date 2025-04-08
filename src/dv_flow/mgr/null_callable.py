import dataclasses as dc
from .task_data import TaskDataResult

@dc.dataclass
class NullCallable(object):
    body : str

    async def __call__(self, ctxt, input):
        """Null callable that does nothing"""
        return TaskDataResult()
