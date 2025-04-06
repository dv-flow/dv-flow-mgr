import dataclasses as dc
import logging
from typing import ClassVar, List
from .task_data import TaskDataResult

@dc.dataclass
class PytaskCallable(object):
    run : str
    _log : ClassVar = logging.getLogger("PytaskCallable")

    async def __call__(self, ctxt, input):
        self._log.debug("--> ExecCallable")
        self._log.debug("Body:\n%s" % "\n".join(self.body))
        method = "async def pytask(ctxt, input):\n" + "\n".join(["    %s" % l for l in self.body])

        exec(method)

        result = await locals()['pytask'](ctxt, input)

        if result is None:
            result = TaskDataResult()

        self._log.debug("<-- ExecCallable")
        return result

