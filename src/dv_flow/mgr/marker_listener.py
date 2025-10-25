import abc
from typing import Protocol
from .task_data import TaskMarker

class MarkerListener(Protocol):

    @abc.abstractmethod
    def marker(self, m : TaskMarker): pass

    pass