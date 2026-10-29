"""Live run events (event_sink.py, task_listener_events.py): the protocol a
dashboard or IDE collects through DFM_EVENT_SINK."""
import asyncio
import json
import os
import socket
import textwrap
import threading
import time

import pytest
from pydantic import BaseModel

from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr import event_sink
from dv_flow.mgr.event_sink import (
    EventEmitter, FileSink, UnixSink, ctx_block, new_sid, parse_sinks)
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE
from dv_flow.mgr.task_listener_events import TaskListenerEvents
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf


class EmptyParams(BaseModel):
    pass


def read_lines(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def by_ev(lines, ev):
    return [l for l in lines if l["ev"] == ev]


# --- the sink layer -------------------------------------------------------

def test_sid_is_a_time_ordered_ulid():
    a = new_sid(now=1000.0)
    b = new_sid(now=1001.0)
    assert len(a) == 26 and len(b) == 26
    assert a < b
    assert new_sid() != new_sid()


def test_ctx_matches_names_and_prefixes():
    env = {"WPK_PROJECT": "p", "WPK_STEP": "3", "HOME": "/h", "OTHER": "x"}
    ctx, trunc = ctx_block("WPK_*, HOME, MISSING", env)
    assert ctx == {"HOME": "/h", "WPK_PROJECT": "p", "WPK_STEP": "3"}
    assert not trunc
    assert ctx_block(None, env) == ({}, False)
    assert ctx_block("", env) == ({}, False)


def test_ctx_is_capped():
    env = {"V%03d" % i: "x" for i in range(200)}
    ctx, trunc = ctx_block("*", env)
    assert len(ctx) == event_sink.CTX_MAX_ENTRIES and trunc
    env = {"A": "a" * 3000, "B": "b" * 3000}
    ctx, trunc = ctx_block("*", env)
    assert list(ctx) == ["A"] and trunc


def test_parse_sinks():
    sinks = parse_sinks("unix:/tmp/s.sock, file:/tmp/e.jsonl,file:///tmp/f,tcp:h:1,bogus,")
    assert [type(s) for s in sinks] == [UnixSink, FileSink, FileSink]
    assert sinks[0].path == "/tmp/s.sock"
    assert sinks[1].path == "/tmp/e.jsonl"
    assert sinks[2].path == "/tmp/f"
    assert parse_sinks(None) == [] and parse_sinks("") == []


def test_unset_sink_gives_no_emitter():
    assert EventEmitter.from_env({}) is None


def test_dead_socket_gives_no_emitter_quickly(tmp_path):
    t0 = time.monotonic()
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "unix:%s" % (tmp_path / "none.sock")})
    assert em is None
    assert time.monotonic() - t0 < 1.0


def test_envelope_and_seq(tmp_path):
    path = tmp_path / "ev.jsonl"
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path,
                                "DFM_EVENT_CTX": "WPK_*", "WPK_WPID": "w1",
                                "DFM_EVENT_PARENT": "PARENTSID"})
    assert em is not None and em.parent == "PARENTSID"
    em.emit("run.start", **em.origin())
    em.emit("task.state", id="a", state="run")
    em.close("run.end", status=0)
    lines = read_lines(path)
    assert [l["seq"] for l in lines] == [0, 1, 2]
    assert all(l["v"] == 1 and l["src"] == "dfm" and l["sid"] == em.sid for l in lines)
    start = lines[0]
    assert start["ctx"] == {"WPK_WPID": "w1"}
    assert start["parent"] == "PARENTSID"
    assert start["pid"] == os.getpid()
    assert lines[-1]["ev"] == "run.end" and lines[-1]["dropped"] == 0
    em.emit("late", x=1)        # after close: ignored
    assert len(read_lines(path)) == 3


def test_overflow_drops_and_counts(tmp_path, monkeypatch):
    """A collector that stops reading must not block the run; the overflow is
    dropped and reported in run.end."""
    monkeypatch.setattr(event_sink, "QUEUE_MAX", 4)
    monkeypatch.setattr(event_sink, "SEND_TIMEOUT_S", 0.3)
    monkeypatch.setattr(event_sink, "CLOSE_TIMEOUT_S", 0.4)
    sock_path = str(tmp_path / "s.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    try:
        em = EventEmitter.from_env({"DFM_EVENT_SINK": "unix:%s" % sock_path})
        assert em is not None
        conn, _ = srv.accept()
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        t0 = time.monotonic()
        for i in range(2000):
            em.emit("task.state", id="t%d" % i, state="run", pad="x" * 512)
        assert time.monotonic() - t0 < 1.0
        assert em.dropped > 0
        em.close("run.end", status=0)
        assert time.monotonic() - t0 < 3.0
        conn.close()
    finally:
        srv.close()


def test_unix_sink_delivers_lines(tmp_path):
    sock_path = str(tmp_path / "s.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    got = []

    def serve():
        conn, _ = srv.accept()
        buf = b""
        while True:
            d = conn.recv(65536)
            if not d:
                break
            buf += d
        got.extend(json.loads(l) for l in buf.decode().splitlines())
        conn.close()

    th = threading.Thread(target=serve)
    th.start()
    try:
        em = EventEmitter.from_env({"DFM_EVENT_SINK": "unix:%s" % sock_path})
        em.emit("run.start", x=1)
        em.close("run.end", status=0)
        th.join(5)
    finally:
        srv.close()
    assert [l["ev"] for l in got] == ["run.start", "run.end"]


def test_peer_gone_disables_sink_without_failing(tmp_path):
    sock_path = str(tmp_path / "s.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "unix:%s" % sock_path})
    conn, _ = srv.accept()
    conn.close()
    srv.close()
    for i in range(200):
        em.emit("task.state", id="t", state="run", pad="x" * 1024)
    em.close("run.end", status=0)
    assert em.sinks[0].disabled


# --- runner level ---------------------------------------------------------

def _ctxt(tmp_path):
    rundir = tmp_path / "rundir"
    rundir.mkdir(exist_ok=True)
    return str(rundir), TaskNodeCtxt(root_pkgdir=str(tmp_path),
                                     root_rundir=str(rundir),
                                     env=os.environ.copy())


def _run_with_events(tmp_path, roots, rundir, nproc=1):
    path = tmp_path / "events.jsonl"
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path})
    events = TaskListenerEvents(em, roots=[r.name for r in roots], rundir=rundir)
    runner = TaskSetRunner(rundir=rundir, nproc=nproc)
    runner.add_event_listener(events.event)
    asyncio.run(runner.run(roots))
    events.close(runner)
    return runner, read_lines(path)


def test_plan_states_skips_markers_and_exec(tmp_path):
    rundir, nctxt = _ctxt(tmp_path)

    async def ok(ctxt, input):
        status = await ctxt.exec(["true"], logfile="true.log")
        ctxt.info("live note")
        return TaskDataResult(status=status, output=[], markers=[
            TaskMarker(msg="returned note", severity=SeverityE.Warning)])

    async def bad(ctxt, input):
        ctxt.error("it broke")
        return TaskDataResult(status=1, output=[])

    def leaf(name, fn, needs=()):
        return TaskNodeLeaf(name=name, srcdir=str(tmp_path), params=EmptyParams(),
                            ctxt=nctxt, task=fn, needs=[(n, False) for n in needs])

    a = leaf("a", ok)
    b = leaf("b", bad, [a])
    c = leaf("c", ok, [b])
    d = leaf("d", ok, [c])
    e = leaf("e", ok, [a])

    runner, lines = _run_with_events(tmp_path, [d, e], rundir)
    assert runner.status != 0

    assert lines[0]["ev"] == "run.start"
    assert lines[0]["roots"] == ["d", "e"]
    assert lines[0]["rundir"] == os.path.abspath(rundir)
    assert lines[-1]["ev"] == "run.end"
    assert lines[-1]["result"] == "fail"
    assert [l["seq"] for l in lines] == list(range(len(lines)))

    plan = by_ev(lines, "graph.plan")
    assert len(plan) == 1
    nodes = {n["id"]: n for n in plan[0]["nodes"]}
    assert set(nodes) == {"a", "b", "c", "d", "e"}
    assert nodes["d"]["needs"] == [{"id": "c", "block": False}]
    assert nodes["a"]["kind"] == "leaf"

    final = {}
    for l in by_ev(lines, "task.state"):
        if l["state"] in ("done", "skipped"):
            final[l["id"]] = l
    assert set(final) == set(nodes)
    assert final["a"]["state"] == "done" and final["a"]["status"] == 0
    assert final["b"]["state"] == "done" and final["b"]["status"] == 1
    assert final["c"]["state"] == "skipped"
    assert final["d"]["state"] == "skipped"
    # e does not need b, but at -j1 a failure stops new launches; either
    # way it reaches a terminal state
    assert lines[-1]["counts"]["skipped"] == sum(
        1 for f in final.values() if f["state"] == "skipped") >= 2
    assert lines[-1]["counts"]["failed"] == 1

    # Live markers come before their task's done; returned markers at done
    def idx(pred):
        return next(i for i, l in enumerate(lines) if pred(l))
    live = idx(lambda l: l["ev"] == "task.marker" and l["msg"] == "it broke")
    b_done = idx(lambda l: l["ev"] == "task.state" and l["id"] == "b" and l["state"] == "done")
    assert live < b_done
    marks = [(l["id"], l["severity"], l["msg"]) for l in by_ev(lines, "task.marker")]
    assert marks.count(("b", "error", "it broke")) == 1        # not repeated at done
    assert ("a", "info", "live note") in marks
    assert ("a", "warning", "returned note") in marks

    ex = [l for l in by_ev(lines, "task.exec") if l["id"] == "a"]
    assert [l["phase"] for l in ex] == ["start", "end"]
    assert ex[0]["cmd"] == ["true"] and ex[1]["rc"] == 0
    assert ex[0]["logfile"].endswith("true.log")


def test_dynamic_subgraph_extends_the_plan(tmp_path):
    rundir, nctxt = _ctxt(tmp_path)

    async def child(ctxt, input):
        return TaskDataResult(status=0, output=[])

    async def parent(ctxt, input):
        kids = [TaskNodeLeaf(name="kid", srcdir=str(tmp_path), params=EmptyParams(),
                             ctxt=ctxt.ctxt, task=child) for _ in range(2)]
        await ctxt.run_subgraph(kids, name="kids")
        return TaskDataResult(status=0, output=[])

    p = TaskNodeLeaf(name="parent", srcdir=str(tmp_path), params=EmptyParams(),
                     ctxt=nctxt, task=parent)
    runner, lines = _run_with_events(tmp_path, [p], rundir, nproc=2)
    assert runner.status == 0

    ext = by_ev(lines, "graph.extend")
    assert len(ext) == 1 and ext[0]["scope"] == "kids"
    # Two nodes with one name get distinct ids
    assert sorted(n["id"] for n in ext[0]["nodes"]) == ["kid", "kid#2"]
    done = {l["id"] for l in by_ev(lines, "task.state") if l["state"] == "done"}
    assert done == {"parent", "kid", "kid#2"}
    assert lines[-1]["ev"] == "run.end" and lines[-1]["result"] == "ok"


def test_listener_error_does_not_fail_run(tmp_path):
    rundir, nctxt = _ctxt(tmp_path)

    async def ok(ctxt, input):
        return TaskDataResult(status=0, output=[])

    def broken(subject, reason, info):
        raise RuntimeError("boom")

    t = TaskNodeLeaf(name="t", srcdir=str(tmp_path), params=EmptyParams(),
                     ctxt=nctxt, task=ok)
    runner = TaskSetRunner(rundir=rundir)
    runner.add_event_listener(broken)
    asyncio.run(runner.run(t))
    assert runner.status == 0


# --- dfm run (CmdRun) -----------------------------------------------------

class Args:
    def __init__(self, root, tasks):
        self.tasks = tasks
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root


FLOW = textwrap.dedent('''\
    package:
      name: evflow
      tasks:
      - name: first
        shell: bash
        run: echo "$DFM_EVENT_PARENT" > parent.txt
      - name: second
        uses: std.Message
        needs: [first]
        with:
          msg: hello
    ''')


def test_cmd_run_reports_to_file_sink(tmp_path, monkeypatch):
    (tmp_path / "flow.yaml").write_text(FLOW)
    sink = tmp_path / "events.jsonl"
    monkeypatch.setenv("DFM_EVENT_SINK", "file:%s" % sink)
    monkeypatch.setenv("DFM_EVENT_CTX", "WPK_*")
    # Isolate from WPK_* variables in the caller's environment
    for k in [k for k in os.environ if k.startswith("WPK_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("WPK_WPID", "wp-1")
    monkeypatch.delenv("DFM_EVENT_PARENT", raising=False)
    monkeypatch.chdir(tmp_path)
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    status = CmdRun()(Args(str(tmp_path), ["second"]))
    assert status == 0

    lines = read_lines(sink)
    start = lines[0]
    assert start["ev"] == "run.start"
    assert start["ctx"] == {"WPK_WPID": "wp-1"}
    assert start["roots"] == ["evflow.second"]
    assert "parent" not in start
    assert lines[-1]["ev"] == "run.end" and lines[-1]["status"] == 0

    plan = by_ev(lines, "graph.plan")[0]
    ids = {n["id"] for n in plan["nodes"]}
    assert {"evflow.first", "evflow.second"} <= ids
    done = {l["id"] for l in by_ev(lines, "task.state") if l["state"] == "done"}
    assert ids <= done

    # Tasks see this run's sid as DFM_EVENT_PARENT, so a separate dfm they
    # start nests under it.
    found = [os.path.join(d, "parent.txt") for d, _, f in os.walk(tmp_path) if "parent.txt" in f]
    assert found
    assert open(found[0]).read().strip() == start["sid"]


def test_cmd_run_with_dead_socket(tmp_path, monkeypatch):
    (tmp_path / "flow.yaml").write_text(FLOW)
    monkeypatch.setenv("DFM_EVENT_SINK", "unix:%s" % (tmp_path / "nobody.sock"))
    monkeypatch.chdir(tmp_path)
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    status = CmdRun()(Args(str(tmp_path), ["second"]))
    assert status == 0


# --- heartbeat ------------------------------------------------------------

def test_heartbeat_names_what_is_running(tmp_path):
    rundir, nctxt = _ctxt(tmp_path)

    async def slow(ctxt, input):
        await asyncio.sleep(0.45)
        return TaskDataResult(status=0, output=[])

    t = TaskNodeLeaf(name="slow", srcdir=str(tmp_path), params=EmptyParams(),
                     ctxt=nctxt, task=slow)
    path = tmp_path / "events.jsonl"
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path,
                                "DFM_EVENT_HEARTBEAT": "0.1"})
    events = TaskListenerEvents(em, roots=["slow"], rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)
    runner.add_event_listener(events.event)
    asyncio.run(runner.run(t))
    events.close(runner)
    lines = read_lines(path)

    alive = by_ev(lines, "run.alive")
    assert len(alive) >= 2
    assert all(a["running"] == ["slow"] and a["n_running"] == 1 for a in alive)
    assert [l["seq"] for l in lines] == list(range(len(lines)))
    assert lines[0]["ev"] == "run.start" and lines[-1]["ev"] == "run.end"


def test_heartbeat_only_when_quiet(tmp_path):
    path = tmp_path / "ev.jsonl"
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path,
                                "DFM_EVENT_HEARTBEAT": "0.2"})
    em.emit("run.start")
    em.start_heartbeat()
    for _ in range(10):
        em.emit("task.state", id="t", state="run")
        time.sleep(0.05)
    em.close("run.end")
    assert by_ev(read_lines(path), "run.alive") == []


def test_heartbeat_off(tmp_path):
    path = tmp_path / "ev.jsonl"
    em = EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path,
                                "DFM_EVENT_HEARTBEAT": "0"})
    assert em.heartbeat_s == 0
    em.emit("run.start")
    em.start_heartbeat()
    time.sleep(0.2)
    em.close("run.end")
    assert by_ev(read_lines(path), "run.alive") == []
    assert EventEmitter.from_env({"DFM_EVENT_SINK": "file:%s" % path,
                                  "DFM_EVENT_HEARTBEAT": "junk"}).heartbeat_s == event_sink.HEARTBEAT_S
