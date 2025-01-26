from ..task import Task
from ..task_data import TaskData

class TaskNull(Task):
    """The Null task simply propagates its input to its output"""

    async def run(self, input : TaskData) -> TaskData:
        # No memento ; data pass-through
        self._log.debug("%s: TaskNull.run" % self.name)
        return input

