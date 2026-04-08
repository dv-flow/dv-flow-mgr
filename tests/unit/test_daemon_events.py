"""Tests for daemon_events: serialization, parsing, known event types."""
import json
import pytest
from dv_flow.mgr.daemon_events import (
    make_event, parse_event, is_known_event,
    EVENT_WORKER_STATE, EVENT_TASK_DISPATCHED, EVENT_TASK_COMPLETED,
    EVENT_POOL_SCALED, EVENT_CLIENT_CONNECTED, EVENT_LOG,
)


class TestMakeEvent:
    def test_worker_state(self):
        raw = make_event(EVENT_WORKER_STATE, {"worker_id": "w1", "state": "idle"})
        data = json.loads(raw)
        assert data["method"] == "worker.state"
        assert data["params"]["worker_id"] == "w1"

    def test_task_dispatched(self):
        raw = make_event(EVENT_TASK_DISPATCHED, {"request_id": "r1", "name": "t1"})
        data = json.loads(raw)
        assert data["method"] == "task.dispatched"

    def test_log_event(self):
        raw = make_event(EVENT_LOG, {"msg": "hello"})
        data = json.loads(raw)
        assert data["params"]["msg"] == "hello"


class TestParseEvent:
    def test_valid_event(self):
        raw = json.dumps({"method": "worker.state", "params": {"worker_id": "w1"}})
        ev = parse_event(raw)
        assert ev is not None
        assert ev["method"] == "worker.state"
        assert ev["params"]["worker_id"] == "w1"

    def test_empty_string(self):
        assert parse_event("") is None

    def test_invalid_json(self):
        assert parse_event("{bad json") is None

    def test_non_object(self):
        assert parse_event('"just a string"') is None

    def test_round_trip(self):
        for method in [EVENT_WORKER_STATE, EVENT_TASK_DISPATCHED,
                       EVENT_TASK_COMPLETED, EVENT_POOL_SCALED,
                       EVENT_CLIENT_CONNECTED, EVENT_LOG]:
            raw = make_event(method, {"key": "value"})
            ev = parse_event(raw)
            assert ev["method"] == method
            assert ev["params"]["key"] == "value"

    def test_unknown_event_parsed(self):
        """Unknown event types are parsed without error."""
        raw = json.dumps({"method": "unknown.event", "params": {"x": 1}})
        ev = parse_event(raw)
        assert ev is not None
        assert ev["method"] == "unknown.event"


class TestIsKnownEvent:
    def test_known_events(self):
        for method in [EVENT_WORKER_STATE, EVENT_TASK_DISPATCHED,
                       EVENT_TASK_COMPLETED, EVENT_POOL_SCALED,
                       EVENT_CLIENT_CONNECTED, EVENT_LOG]:
            assert is_known_event(method) is True

    def test_unknown_event(self):
        assert is_known_event("unknown.method") is False
