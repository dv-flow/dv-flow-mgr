import dataclasses as dc
import logging
from typing import ClassVar, List
from .task_data import TaskDataResult
from .pytask import PyTask
from .exec_callable import _merge_env_filesets



@dc.dataclass
class PytaskCallable(object):
    run : str
    _log : ClassVar = logging.getLogger("PytaskCallable")

    async def __call__(self, ctxt, input):
        self._log.debug("--> ExecCallable")
        self._log.debug("Body:\n%s" % "\n".join(self.body))

        # Merge std.Env filesets into context environment for exec
        env = _merge_env_filesets(ctxt, input)
        ctxt.env.update(env)

        method = "async def pytask(ctxt, input):\n" + "\n".join(["    %s" % l for l in self.body])

        exec(method)

        result = await locals()['pytask'](ctxt, input)

        if result is None:
            result = TaskDataResult()

        self._log.debug("<-- ExecCallable")
        return result

    def _merge_env_filesets(self, ctxt, input):
        """Deprecated: use dv_flow.mgr.exec_callable._merge_env_filesets instead."""
        return _merge_env_filesets(ctxt, input)
