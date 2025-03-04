import dataclasses as dc

class TaskListenerLog(object):

    def event(self, task : 'Task', reason : 'Reason'):
        if reason == 'enter':
            print("> Task %s" % task.name, flush=True)
        elif reason == 'leave':
            for m in task.result.markers:
                print("  %s" % m)
            print("< Task %s" % task.name, flush=True)
        else:
            print("- Task %s" % task.name, flush=True)
        pass

