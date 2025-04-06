import dataclasses as dc
import logging
from dv_flow.mgr import TaskMarker
from typing import ClassVar, List

@dc.dataclass
class MarkerCollector(object):
    markers : List[TaskMarker] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger("MarkerCollector")

    def __call__(self, marker):
        if marker.loc is not None:
            path = " @ %s" % marker.loc.path
            if marker.loc.line != -1:
                path += ":%d" % marker.loc.line
            if marker.loc.pos != -1:
                path += ":%d" % marker.loc.pos
        else:
            path = ""

        self._log.debug("%s: %s%s" % (str(marker.severity), marker.msg, path))
        self.markers.append(marker)