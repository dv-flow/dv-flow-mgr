import dataclasses as dc
import logging
from typing import ClassVar, List
from .task_data import TaskDataResult
from .pytask import PyTask

def _merge_env_filesets(ctxt, input):
    """Collect std.Env filesets from inputs and merge them into the context environment."""
    env = ctxt.env.copy()
    # Merge std.Env data items from inputs
    # Collect all std.Env vals in dependency order, oldest first
    env_items = []
    for item in getattr(input, "inputs", []):
        if getattr(item, "type", None) == "std.Env" and hasattr(item, "vals") and isinstance(item.vals, dict):
            env_items.append(item.vals)
    # Merge all keys from all std.Env, oldest first, newest override
    merged_env = {}
    for vals in env_items:
        for k, v in vals.items():
            merged_env[k] = v
    env.update(merged_env)
    return env

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

@dc.dataclass
class PytaskClassCallable(object):
    run : PyTask = dc.field()
    _log : ClassVar = logging.getLogger("PytaskCallable")

    async def __call__(self, ctxt, input):
        self._log.debug("--> PyTask")

        # Merge std.Env filesets into context environment for exec
        env = _merge_env_filesets(ctxt, input)
        ctxt.env.update(env)

        self.run._ctxt = ctxt
        self.run._input = input

        await self.run.run()

        self._log.debug("<-- PyTask")

        if result is None:
            result = TaskDataResult()

        self._log.debug("<-- ExecCallable")
        return result
