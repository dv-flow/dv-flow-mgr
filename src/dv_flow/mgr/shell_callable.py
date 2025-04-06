import dataclasses as dc
import logging
from typing import ClassVar, List
from .task_data import TaskDataResult

@dc.dataclass
class ShellCallable(object):
    body : str
    shell : str
    _log : ClassVar = logging.getLogger("ShellCallable")

    async def __call__(self, ctxt, input):
        pass

