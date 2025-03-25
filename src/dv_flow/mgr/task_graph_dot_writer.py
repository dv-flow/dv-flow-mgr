import dataclasses as dc
import logging
import sys
from typing import ClassVar, Dict, TextIO
from .task_node import TaskNode
from .task_node_compound import TaskNodeCompound

@dc.dataclass
class TaskGraphDotWriter(object):
    fp : TextIO = dc.field(default=None)
    _ind : str = ""
    _node_id_m : Dict[TaskNode, str] = dc.field(default_factory=dict)
    _node_id : int = 1
    _cluster_id : int = 1
    _log : ClassVar = logging.getLogger("TaskGraphDotWriter")

    def write(self, node, filename):
        self._log.debug("--> TaskGraphDotWriter::write")

        if filename == "-":
            self.fp = sys.stdout
        else:
            self.fp = open(filename, "w")
        self.println("digraph G {")
        self.process_node(node)
        self.println("}")

        self.fp.close()
        self._log.debug("<-- TaskGraphDotWriter::write")

    def process_node(self, node):
        self._log.debug("--> process_node %s (%d)" % (node.name, len(node.needs),))
        node_id = self._node_id
        self._node_id += 1
        node_name = "n%d" % self._node_id
        self._node_id_m[node] = node_name

        if isinstance(node, TaskNodeCompound):
            self.println("subgraph cluster_%d {" % self._cluster_id)
            self._cluster_id += 1
            self.inc_ind()
            self.println("label=\"%s\";" % node.name)
            self.println("color=blue;")
            self.println("style=dashed;")
            self.process_node(node.input)

            self.println("%s[label=\"%s.out\"];" % (
                node_name,
                node.name))
        else:
            self.println("%s[label=\"%s\"];" % (
                node_name,
                node.name))

        for dep in node.needs:
            if dep[0] not in self._node_id_m.keys():
                self.process_node(dep[0])
            self.println("%s -> %s;" % (
                self._node_id_m[dep[0]],
                self._node_id_m[node]))
            
        if isinstance(node, TaskNodeCompound):
            self.dec_ind()
            self.println("}")

        self._log.debug("<-- process_node %s (%d)" % (node.name, len(node.needs),))

    def println(self, l):
        self.fp.write("%s%s\n" % (self._ind, l))
    
    def inc_ind(self):
        self._ind += "  "
    
    def dec_ind(self):
        if len(self._ind) > 4:
            self._ind = self._ind[4:]
        else:
            self._ind = ""
