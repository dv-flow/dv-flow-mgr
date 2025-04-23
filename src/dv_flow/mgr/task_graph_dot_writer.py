import dataclasses as dc
import logging
import sys
from typing import ClassVar, Dict, Set, TextIO
from .task_node import TaskNode
from .task_node_compound import TaskNodeCompound

@dc.dataclass
class TaskGraphDotWriter(object):
    fp : TextIO = dc.field(default=None)
    _ind : str = ""
    _node_id_m : Dict[TaskNode, str] = dc.field(default_factory=dict)
    _processed_needs : Set[TaskNode] = dc.field(default_factory=set)
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
        # First, build-out all nodes
        self.build_node(node)
        self.process_needs(node)
        self.println("}")

        self.fp.close()
        self._log.debug("<-- TaskGraphDotWriter::write")

    def build_node(self, node):
        self._log.debug("--> build_node %s (%d)" % (node.name, len(node.needs),))

        if isinstance(node, TaskNodeCompound):
            self._log.debug("-- compound node")
            # Find the root and build out any expanded sub-nodes
            root = node
            while root.parent is not None:
                root = root.parent
            self.build_compound_node(root)
        else:
            # Leaf node
            self._log.debug("-- leaf node")
            node_id = self._node_id
            self._node_id += 1
            node_name = "n%d" % node_id
            self._node_id_m[node] = node_name
            self.println("%s[label=\"%s\",tooltip=\"%s\"];" % (
                node_name, 
                node.name,
                self._genLeafTooltip(node)))
        self._log.debug("<-- build_node %s (%d)" % (node.name, len(node.needs),))

    def _genLeafTooltip(self, node):
        params = type(node.params).model_fields
        ret = ""
        if len(params):
            ret += "Parameters:\\n"
            for k in type(node.params).model_fields.keys():
                ret += "- %s: " % k
                v = getattr(node.params, k)
                if isinstance(v, str):
                    ret += "%s" % v
                elif isinstance(v, list):
                    ret += "[%s]" % ", ".join([str(x) for x in v])
                elif isinstance(v, dict):
                    ret += "{%s}" % ", ".join(["%s: %s" % (str(k), str(v)) for k,v in v.items()])
                else:
                    ret += "%s" % str(v)
                ret += "\\n"
        return ret

    def process_needs(self, node):
        self._log.debug("--> process_needs %s (%d)" % (node.name, len(node.needs),))

        # if isinstance(node, TaskNodeCompound):
        #     self.println("subgraph cluster_%d {" % self._cluster_id)
        #     self._cluster_id += 1
        #     self.inc_ind()
        #     self.println("label=\"%s\";" % node.name)
        #     self.println("color=blue;")
        #     self.println("style=dashed;")
        #     self.process_node(node.input)

        #     self.println("%s[label=\"%s.out\"];" % (
        #         node_name,
        #         node.name))
        # else:
        #     self.println("%s[label=\"%s\"];" % (
        #         node_name,
        #         node.name))

        for dep,_ in node.needs:
            if dep not in self._node_id_m.keys():
                self.build_node(dep)
            if dep not in self._node_id_m.keys():
                self._log.error("Dep-node not built: %s" % dep.name)
            if node not in self._node_id_m.keys():
                self.build_node(node)
            if node not in self._node_id_m.keys():
                self._log.error("Dep-node not built: %s" % node.name)
            self.println("%s -> %s;" % (
                self._node_id_m[dep],
                self._node_id_m[node]))
            if dep not in self._processed_needs:
                self._processed_needs.add(dep)
                self.process_needs(dep)
            
        self._log.debug("<-- process_needs %s (%d)" % (node.name, len(node.needs),))

    def build_compound_node(self, node):
        """Hierarchical build of a compound root node"""

        self._log.debug("--> build_compound_node %s (%d)" % (node.name, len(node.tasks),))

        id = self._cluster_id
        self._cluster_id += 1
        self.println("subgraph cluster_%d {" % id)
        self.inc_ind()
        self.println("label=\"%s\";" % node.name)
        self.println("tooltip=\"%s\";" % self._genLeafTooltip(node))
        self.println("color=blue;")
        self.println("style=dashed;")

        task_node_id = self._node_id
        self._node_id += 1
        task_node_name = "n%d" % task_node_id
        self.println("%s[label=\"%s\", tooltip=\"%s\"];" % (
            task_node_name, 
            node.name,
            self._genLeafTooltip(node)))
        self._node_id_m[node] = task_node_name

        for n in node.tasks:
            if isinstance(n, TaskNodeCompound):
                # Recurse
                self.build_compound_node(n)
            else:
                # Leaf node
                node_id = self._node_id
                self._node_id += 1
                node_name = "n%d" % node_id
                self._node_id_m[n] = node_name
                leaf_name = n.name[n.name.rfind(".") + 1:]
                self.println("%s[label=\"%s\",tooltip=\"%s\"];" % (
                    node_name, 
                    leaf_name,
                    self._genLeafTooltip(n)))
        self.dec_ind()
        self.println("}")

        self._log.debug("<-- build_compound_node %s (%d)" % (node.name, len(node.tasks),))

    def println(self, l):
        self.fp.write("%s%s\n" % (self._ind, l))
    
    def inc_ind(self):
        self._ind += "  "
    
    def dec_ind(self):
        if len(self._ind) > 4:
            self._ind = self._ind[4:]
        else:
            self._ind = ""
