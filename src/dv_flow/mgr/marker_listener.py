import abc
from .task_data import TaskMarker

class MarkerListener(object):

    @abc.abstractmethod
    def marker(self, m : TaskMarker): pass

    pass