import dataclasses as dc

@dc.dataclass
class TaskListenerTest(object):
    events : int = 0
    completed : int = 0

    def event(self, task, reason):
        self.events += 1
        if reason == "leave":
            self.completed += 1