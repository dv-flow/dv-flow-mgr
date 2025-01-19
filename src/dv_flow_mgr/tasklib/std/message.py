
from dv_flow_mgr import Task, TaskData

class Message(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("Message: %s" % self.params.msg)
        return input
