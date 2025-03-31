import dataclasses as dc
from typing import List, Callable

@dc.dataclass
class ListenerList(object):
    listeners : List[Callable] = dc.field(default_factory=list)

    def __call__(self, *args, **kwargs):
        for l in self.listeners:
            l(*args, **kwargs)
