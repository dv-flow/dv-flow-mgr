"""The `node_url` hook on TaskGraphDotWriter.

A dot graph rendered to SVG is the natural index of a flow -- but only if the
boxes are links. The writer can't know where a task's documentation lives, so
it takes a callback and stays out of it.
"""
import io
import os

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector


FLOW = """
package:
    name: foo

    tasks:
    - name: leaf
      uses: std.Message
      with:
        msg: hello
    - name: entry
      body:
      - name: inner
        uses: std.Message
        with:
          msg: inner
"""


def _build(tmpdir, task="foo.entry"):
    rundir = str(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(FLOW)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    assert [m.msg for m in collector.markers] == []
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(rundir, "rundir"))
    return builder.mkTaskNode(task, name="t1")


def _write(node, **kwargs):
    buf = io.StringIO()
    TaskGraphDotWriter(**kwargs).write(node, buf)
    return buf.getvalue()


def test_no_hook_emits_no_urls(tmpdir):
    """The default output is byte-for-byte what it was before the hook."""
    node = _build(tmpdir)
    assert "URL=" not in _write(node)


def test_hook_adds_urls_to_leaf_nodes(tmpdir):
    node = _build(tmpdir, task="foo.leaf")
    dot = _write(node, node_url=lambda n: "/tasks/%s.html" % n.name)
    assert 'URL="/tasks/t1.html"' in dot


def test_hook_adds_url_to_compound_cluster(tmpdir):
    """A compound's link goes on the cluster box -- the thing a reader points
    at when they mean the whole task -- not on its synthetic exit point."""
    node = _build(tmpdir)
    dot = _write(node, node_url=lambda n: "/tasks/%s.html" % n.name)
    lines = [l.strip() for l in dot.split("\n")]
    assert 'URL="/tasks/t1.html";' in lines


def test_hook_returning_none_leaves_node_bare(tmpdir):
    """Not every node has a documentation page. Skipping the link must not
    skip the node."""
    node = _build(tmpdir, task="foo.leaf")
    dot = _write(node, node_url=lambda n: None)
    assert "URL=" not in dot
    assert "t1" in dot


def test_failing_hook_does_not_fail_the_graph(tmpdir):
    """The topology is the point; the links are an enhancement. A hook that
    raises costs its own node's link and nothing else."""
    def boom(n):
        raise RuntimeError("no url for you")

    node = _build(tmpdir, task="foo.leaf")
    dot = _write(node, node_url=boom)
    assert "URL=" not in dot
    assert "digraph G {" in dot
    assert "t1" in dot


def test_url_is_escaped(tmpdir):
    """A URL with a quote in it must not close the attribute early."""
    node = _build(tmpdir, task="foo.leaf")
    dot = _write(node, node_url=lambda n: '/a"b\\c.html')
    assert 'URL="/a\\"b\\\\c.html"' in dot


def test_hook_composes_with_show_params(tmpdir):
    """Record-shaped nodes take the URL attribute too."""
    node = _build(tmpdir, task="foo.leaf")
    dot = _write(node, show_params=True,
                 node_url=lambda n: "/tasks/%s.html" % n.name)
    assert "shape=record" in dot
    assert 'URL="/tasks/t1.html"' in dot
