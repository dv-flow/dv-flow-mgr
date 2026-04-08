"""Tests for worker_protocol: message building and parsing."""
import json
import pytest
from dv_flow.mgr.worker_protocol import (
    build_worker_register,
    build_task_execute,
    build_task_result,
    build_worker_heartbeat,
    build_worker_shutdown,
    parse_message,
    encode_message,
    decode_line,
    ProtocolError,
    METHOD_WORKER_REGISTER,
    METHOD_TASK_EXECUTE,
    METHOD_TASK_RESULT,
    METHOD_WORKER_HEARTBEAT,
    METHOD_WORKER_SHUTDOWN,
)


class TestBuildAndParse:
    """Round-trip: build -> parse for each message type."""

    def test_worker_register(self):
        raw = build_worker_register(
            worker_id="abc123",
            hostname="compute-42",
            pid=12345,
            resource_class="medium",
            lsf_job_id="98765",
        )
        msg = parse_message(raw)
        assert msg["method"] == METHOD_WORKER_REGISTER
        assert msg["params"]["worker_id"] == "abc123"
        assert msg["params"]["hostname"] == "compute-42"
        assert msg["params"]["pid"] == 12345
        assert msg["params"]["resource_class"] == "medium"
        assert msg["params"]["lsf_job_id"] == "98765"

    def test_task_execute(self):
        raw = build_task_execute(
            request_id="req-1",
            name="pkg.compile.gcc",
            callable_spec="dv_flow.mgr.std.fileset.FileSet",
            shell="pytask",
            srcdir="/proj/src",
            rundir="/proj/rundir",
            pythonpath=["/proj/src"],
            params={"type": "verilogSource"},
            inputs=[],
            env={"PATH": "/usr/bin"},
        )
        msg = parse_message(raw)
        assert msg["method"] == METHOD_TASK_EXECUTE
        assert msg["params"]["request_id"] == "req-1"
        assert msg["params"]["name"] == "pkg.compile.gcc"
        assert msg["params"]["callable_spec"] == "dv_flow.mgr.std.fileset.FileSet"
        assert msg["params"]["pythonpath"] == ["/proj/src"]

    def test_task_execute_with_body(self):
        raw = build_task_execute(
            request_id="req-2",
            name="shell_task",
            shell="bash",
            body="echo hello",
        )
        msg = parse_message(raw)
        assert msg["params"]["body"] == "echo hello"

    def test_task_result(self):
        raw = build_task_result(
            request_id="req-1",
            status=0,
            changed=True,
            output=[{"type": "std.FileSet", "files": ["a.sv"]}],
            markers=[],
            memento=None,
        )
        msg = parse_message(raw)
        assert msg["method"] == METHOD_TASK_RESULT
        assert msg["params"]["status"] == 0
        assert msg["params"]["changed"] is True
        assert len(msg["params"]["output"]) == 1

    def test_worker_heartbeat(self):
        raw = build_worker_heartbeat("abc123")
        msg = parse_message(raw)
        assert msg["method"] == METHOD_WORKER_HEARTBEAT
        assert msg["params"]["worker_id"] == "abc123"

    def test_worker_shutdown(self):
        raw = build_worker_shutdown()
        msg = parse_message(raw)
        assert msg["method"] == METHOD_WORKER_SHUTDOWN


class TestParseErrors:
    def test_invalid_json(self):
        with pytest.raises(ProtocolError, match="Invalid JSON"):
            parse_message("{not valid json")

    def test_empty_message(self):
        with pytest.raises(ProtocolError, match="Empty message"):
            parse_message("")

    def test_missing_method(self):
        with pytest.raises(ProtocolError, match="Missing or invalid 'method'"):
            parse_message('{"params": {}}')

    def test_missing_required_fields(self):
        msg = json.dumps({"method": "worker.register", "params": {}})
        with pytest.raises(ProtocolError, match="missing required params"):
            parse_message(msg)

    def test_non_object_message(self):
        with pytest.raises(ProtocolError, match="JSON object"):
            parse_message('"just a string"')

    def test_params_not_object(self):
        msg = json.dumps({"method": "worker.heartbeat", "params": "bad"})
        with pytest.raises(ProtocolError, match="'params' must be a JSON object"):
            parse_message(msg)


class TestUnknownMethod:
    def test_unknown_method_parsed_without_error(self):
        """Unknown methods should be logged but not rejected."""
        raw = json.dumps({"method": "unknown.method", "params": {"foo": "bar"}})
        msg = parse_message(raw)
        assert msg["method"] == "unknown.method"
        assert msg["params"]["foo"] == "bar"


class TestEncoding:
    def test_encode_message(self):
        raw = build_worker_heartbeat("w1")
        encoded = encode_message(raw)
        assert isinstance(encoded, bytes)
        assert encoded.endswith(b"\n")

    def test_decode_line(self):
        data = b'{"method": "test"}\n'
        line = decode_line(data)
        assert line == '{"method": "test"}'


class TestTaskCancel:
    def test_build_and_parse(self):
        from dv_flow.mgr.worker_protocol import build_task_cancel, parse_message
        msg = build_task_cancel("req42")
        parsed = parse_message(msg)
        assert parsed["method"] == "task.cancel"
        assert parsed["params"]["request_id"] == "req42"

    def test_missing_request_id_raises(self):
        from dv_flow.mgr.worker_protocol import parse_message, ProtocolError
        import json
        raw = json.dumps({"method": "task.cancel", "params": {}})
        with pytest.raises(ProtocolError, match="request_id"):
            parse_message(raw)
