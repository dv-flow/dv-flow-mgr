import dataclasses as dc
import logging
from typing import ClassVar, Dict, TextIO
from .task_node import TaskNode

@dc.dataclass
class TaskGraphDotWriter(object):
    fp : TextIO = dc.field(default=None)
    _ind : str = ""
    _node_id_m : Dict[TaskNode, str] = dc.field(default_factory=dict)
    _node_id : int = 1
    _log : ClassVar = logging.getLogger("TaskGraphDotWriter")

    def write(self, node, filename):
        self._log.debug("--> TaskGraphDotWriter::write")

        self.fp = open(filename, "w")
        self.println("digraph G {")
        self.process_node(node)
        self.println("}")

        self.fp.close()
        self._log.debug("<-- TaskGraphDotWriter::write")

    def process_node(self, node):
        node_id = self._node_id
        self._node_id += 1
        node_name = "n%d" % self._node_id
        self._node_id_m[node] = node_name

        self.println("%s[label=\"%s\"];" % (
            node_name,
            node.name))

        for dep in node.needs:
            if dep[0] not in self._node_id_m.keys():
                self.process_node(dep[0])
            self.println("%s -> %s;" % (
                self._node_id_m[dep[0]],
                self._node_id_m[node]))

    def println(self, l):
        self.fp.write("%s%s\n" % (self._ind, l))
