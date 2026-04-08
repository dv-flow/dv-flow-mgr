"""Tests for DaemonMonitor: event handling and top-like rendering."""
import pytest
from rich.layout import Layout
from dv_flow.mgr.daemon_monitor import DaemonMonitor, MAX_LOG_LINES, MAX_COMPLETED
from dv_flow.mgr.daemon_events import (
    EVENT_WORKER_STATE, EVENT_TASK_DISPATCHED,
    EVENT_TASK_COMPLETED, EVENT_LOG,
)


class TestHandleEvent:
    def test_worker_state_adds_worker(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w1", "state": "idle", "hostname": "h1"},
        })
        assert len(m.workers) == 1
        assert m.workers[0]["worker_id"] == "w1"

    def test_worker_state_updates_existing(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w1", "state": "idle"},
        })
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w1", "state": "busy", "current_task": "t1"},
        })
        assert len(m.workers) == 1
        assert m.workers[0]["state"] == "busy"

    def test_task_dispatched(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_TASK_DISPATCHED,
            "params": {"request_id": "r1", "name": "compile"},
        })
        assert len(m.active_tasks) == 1
        assert m.active_tasks[0]["name"] == "compile"

    def test_task_completed_removes_from_active(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_TASK_DISPATCHED,
            "params": {"request_id": "r1", "name": "compile"},
        })
        m._handle_event({
            "method": EVENT_TASK_COMPLETED,
            "params": {"request_id": "r1", "status": 0},
        })
        assert len(m.active_tasks) == 0

    def test_task_completed_moves_to_completed_list(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_TASK_DISPATCHED,
            "params": {"request_id": "r1", "name": "compile"},
        })
        m._handle_event({
            "method": EVENT_TASK_COMPLETED,
            "params": {"request_id": "r1", "status": 0},
        })
        assert len(m.completed_tasks) == 1
        assert m.total_completed == 1
        assert m.completed_tasks[0]["name"] == "compile"

    def test_completed_tasks_capped(self):
        m = DaemonMonitor()
        for i in range(MAX_COMPLETED + 20):
            m._handle_event({
                "method": EVENT_TASK_DISPATCHED,
                "params": {"request_id": "r%d" % i, "name": "t%d" % i},
            })
            m._handle_event({
                "method": EVENT_TASK_COMPLETED,
                "params": {"request_id": "r%d" % i, "status": 0},
            })
        assert len(m.completed_tasks) == MAX_COMPLETED
        assert m.total_completed == MAX_COMPLETED + 20

    def test_log_appended(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_LOG,
            "params": {"msg": "Worker launched"},
        })
        assert "Worker launched" in m.log_lines

    def test_log_buffer_capped(self):
        m = DaemonMonitor()
        for i in range(MAX_LOG_LINES + 50):
            m._handle_event({
                "method": EVENT_LOG,
                "params": {"msg": "line %d" % i},
            })
        assert len(m.log_lines) == MAX_LOG_LINES

    def test_unknown_event_ignored(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": "unknown.event",
            "params": {"foo": "bar"},
        })
        assert len(m.workers) == 0
        assert len(m.active_tasks) == 0


class TestWorkerCounts:
    def test_counts_empty(self):
        m = DaemonMonitor()
        total, idle, busy, pending = m._worker_counts()
        assert total == 0
        assert idle == 0
        assert busy == 0

    def test_counts_mixed(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w1", "state": "idle"},
        })
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w2", "state": "busy"},
        })
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w3", "state": "busy"},
        })
        total, idle, busy, pending = m._worker_counts()
        assert total == 3
        assert idle == 1
        assert busy == 2


class TestRender:
    def test_render_returns_layout(self):
        m = DaemonMonitor()
        layout = m._render()
        assert isinstance(layout, Layout)

    def test_render_has_main_and_status(self):
        m = DaemonMonitor()
        layout = m._render()
        # Layout should have a "main" and a "status" region
        child_names = [c.name for c in layout.children]
        assert "main" in child_names
        assert "status" in child_names

    def test_render_with_data(self):
        m = DaemonMonitor()
        m._handle_event({
            "method": EVENT_WORKER_STATE,
            "params": {"worker_id": "w1", "state": "busy",
                       "hostname": "h1", "resource_class": "medium",
                       "current_task": "compile"},
        })
        m._handle_event({
            "method": EVENT_TASK_DISPATCHED,
            "params": {"request_id": "r1", "name": "compile"},
        })
        m._handle_event({
            "method": EVENT_LOG,
            "params": {"msg": "test message"},
        })
        layout = m._render()
        assert isinstance(layout, Layout)

    def test_status_bar_fixed_size(self):
        m = DaemonMonitor()
        layout = m._render()
        for child in layout.children:
            if child.name == "status":
                assert child.size == 3
