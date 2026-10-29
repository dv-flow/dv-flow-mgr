#****************************************************************************
#* event_sink.py -- live run events for external collectors
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""Send a run's events, one JSON object per line, to the collectors named by
``DFM_EVENT_SINK``.

``DFM_EVENT_SINK`` is a comma-separated list of URIs:

- ``unix:/path/to/sock`` -- connect to a listening Unix socket
- ``file:/path/events.jsonl`` -- append to a file

``DFM_EVENT_HEARTBEAT`` is the heartbeat interval in seconds (default 10;
0 turns it off). After that long with nothing else sent, the emitter sends
``run.alive``, so a collector can tell a quiet run (one long simulation)
from one that died without closing its stream (a file sink, a SIGKILL).

``DFM_EVENT_CTX`` is a comma-separated list of environment variable names
(a trailing ``*`` makes an entry a prefix). The matching variables are sent
back in the ``run.start`` line as ``ctx``, so a collector can tie a run to its
own sessions without DFM knowing anything about them.

A sink must never slow or fail a run. Each sink has a bounded queue drained
by a daemon thread. Events that do not fit are dropped and counted, and the
``run.end`` line reports the count. A sink that cannot be reached, or whose
peer goes away, is disabled for the rest of the run.
"""
import json
import logging
import os
import queue
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional

ENV_SINK = "DFM_EVENT_SINK"
ENV_CTX = "DFM_EVENT_CTX"
ENV_PARENT = "DFM_EVENT_PARENT"
ENV_HEARTBEAT = "DFM_EVENT_HEARTBEAT"

PROTOCOL_VERSION = 1

CONNECT_TIMEOUT_S = 0.2
SEND_TIMEOUT_S = 2.0
CLOSE_TIMEOUT_S = 1.0
QUEUE_MAX = 4096
HEARTBEAT_S = 10.0

CTX_MAX_ENTRIES = 64
CTX_MAX_BYTES = 4096

_log = logging.getLogger("EventSink")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_sid(now: Optional[float] = None) -> str:
    """A ULID: 48 bits of milliseconds, then 80 random bits, in Crockford
    base32. Unique across hosts and sorts by start time."""
    ms = int((time.time() if now is None else now) * 1000) & ((1 << 48) - 1)
    val = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[val & 0x1F])
        val >>= 5
    return "".join(reversed(out))


def ctx_block(spec: Optional[str], env: Dict[str, str]):
    """Select the variables that ``spec`` (the ``DFM_EVENT_CTX`` value) names.

    Returns ``(ctx, truncated)``. Names that are not set are skipped. At most
    CTX_MAX_ENTRIES entries and CTX_MAX_BYTES of values are kept, so a
    careless ``*`` cannot send the whole environment."""
    if not spec:
        return {}, False
    exact = set()
    prefixes = []
    for ent in spec.split(","):
        ent = ent.strip()
        if not ent:
            continue
        if ent.endswith("*"):
            prefixes.append(ent[:-1])
        else:
            exact.add(ent)
    names = sorted(k for k in env
                   if k in exact or any(k.startswith(p) for p in prefixes))
    ctx = {}
    used = 0
    truncated = False
    for k in names:
        v = env[k]
        if len(ctx) >= CTX_MAX_ENTRIES or used + len(v) > CTX_MAX_BYTES:
            truncated = True
            break
        ctx[k] = v
        used += len(v)
    return ctx, truncated


class Sink(object):
    """One destination. Lines go through a bounded queue to a writer thread."""

    def __init__(self, uri: str):
        self.uri = uri
        self.dropped = 0
        self.disabled = False
        self._q = queue.Queue(maxsize=QUEUE_MAX)
        self._thread = None

    def open(self) -> bool:
        try:
            self._open()
        except Exception as e:
            _log.debug("event sink %s unavailable: %s", self.uri, e)
            self.disabled = True
            return False
        self._thread = threading.Thread(
            target=self._drain, name="dfm-event-sink", daemon=True)
        self._thread.start()
        return True

    def put(self, line: bytes):
        if self.disabled:
            return
        try:
            self._q.put_nowait(line)
        except queue.Full:
            self.dropped += 1

    def close(self, last: Optional[bytes] = None):
        """Queue ``last`` (waiting briefly for room), then stop the writer and
        wait up to CLOSE_TIMEOUT_S for it to finish."""
        if self._thread is None:
            return
        if last is not None and not self.disabled:
            try:
                self._q.put(last, timeout=CLOSE_TIMEOUT_S / 2)
            except queue.Full:
                self.dropped += 1
        try:
            self._q.put(None, timeout=CLOSE_TIMEOUT_S / 2)
        except queue.Full:
            pass
        self._thread.join(CLOSE_TIMEOUT_S)
        self._thread = None

    def _drain(self):
        while True:
            line = self._q.get()
            if line is None:
                break
            if self.disabled:
                continue
            try:
                self._write(line)
            except Exception as e:
                _log.debug("event sink %s failed: %s", self.uri, e)
                self.disabled = True
        try:
            self._close()
        except Exception:
            pass

    def _open(self):
        raise NotImplementedError()

    def _write(self, line: bytes):
        raise NotImplementedError()

    def _close(self):
        pass


class UnixSink(Sink):

    def __init__(self, uri: str, path: str):
        super().__init__(uri)
        self.path = path
        self._sock = None

    def _open(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(CONNECT_TIMEOUT_S)
            s.connect(self.path)
            s.settimeout(SEND_TIMEOUT_S)
        except Exception:
            s.close()
            raise
        self._sock = s

    def _write(self, line: bytes):
        self._sock.sendall(line)

    def _close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class FileSink(Sink):
    """Appends with one write per line, so runs that share a file do not
    interleave within a line."""

    def __init__(self, uri: str, path: str):
        super().__init__(uri)
        self.path = path
        self._fd = None

    def _open(self):
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self._fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)

    def _write(self, line: bytes):
        os.write(self._fd, line)

    def _close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def parse_sinks(value: Optional[str]) -> List[Sink]:
    """Parse a ``DFM_EVENT_SINK`` value. Unknown schemes are skipped."""
    sinks = []
    if not value:
        return sinks
    for uri in value.split(","):
        uri = uri.strip()
        if not uri:
            continue
        scheme, sep, rest = uri.partition(":")
        if not sep or not rest:
            _log.debug("event sink %r: no scheme", uri)
        elif scheme == "unix":
            sinks.append(UnixSink(uri, rest))
        elif scheme == "file":
            # Accept file:///abs/path as well as file:/abs/path
            if rest.startswith("//"):
                rest = rest[2:]
            sinks.append(FileSink(uri, rest))
        else:
            _log.debug("event sink %r: unsupported scheme", uri)
    return sinks


class EventEmitter(object):
    """Stamps each event with the envelope and fans it out to the sinks.

    Envelope: ``{"v", "src", "sid", "seq", "t", "ev", ...payload}``. ``seq``
    counts from 0 per ``sid``."""

    def __init__(self, sinks: List[Sink], env: Optional[Dict[str, str]] = None,
                 sid: Optional[str] = None):
        self.env = dict(os.environ if env is None else env)
        self.sid = sid if sid is not None else new_sid()
        self.parent = self.env.get(ENV_PARENT) or None
        self.sinks = [s for s in sinks if s.open()]
        self._seq = 0
        self._lock = threading.Lock()
        self._closed = False
        self._last = time.monotonic()
        self.heartbeat_s = _heartbeat_interval(self.env.get(ENV_HEARTBEAT))
        self._hb_stop = threading.Event()
        self._hb_thread = None
        self._hb_payload = None

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> Optional['EventEmitter']:
        """An emitter for ``DFM_EVENT_SINK``, or None if it is unset or no
        sink could be opened."""
        env = os.environ if env is None else env
        sinks = parse_sinks(env.get(ENV_SINK))
        if not sinks:
            return None
        em = cls(sinks, env=env)
        if not em.sinks:
            return None
        return em

    @property
    def active(self) -> bool:
        return not self._closed and any(not s.disabled for s in self.sinks)

    @property
    def dropped(self) -> int:
        return sum(s.dropped for s in self.sinks)

    def origin(self) -> Dict[str, Any]:
        """The run.start block that says who sent the stream and from where."""
        ctx, truncated = ctx_block(self.env.get(ENV_CTX), self.env)
        o = {
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "uid": os.getuid() if hasattr(os, "getuid") else None,
            "cwd": os.getcwd(),
            "argv": _trunc_argv(sys.argv),
            "ctx": ctx,
        }
        if truncated:
            o["ctx_truncated"] = True
        term = {}
        for k in ("TERM_PROGRAM", "VSCODE_IPC_HOOK_CLI"):
            if self.env.get(k):
                term[k] = self.env[k]
        if term:
            o["term"] = term
        if self.parent:
            o["parent"] = self.parent
        return o

    def _line(self, ev: str, payload: Dict[str, Any]) -> bytes:
        rec = {"v": PROTOCOL_VERSION, "src": "dfm", "sid": self.sid,
               "seq": self._seq, "t": round(time.time(), 6), "ev": ev}
        rec.update(payload)
        self._seq += 1
        return (json.dumps(rec, default=str, separators=(",", ":")) + "\n").encode()

    def start_heartbeat(self, payload=None):
        """Send ``run.alive`` whenever ``heartbeat_s`` passes with nothing
        else sent. ``payload`` is called (on the heartbeat thread) for the
        line's fields; it must be cheap and must not raise."""
        if self._hb_thread is not None or not self.heartbeat_s or self._closed:
            return
        self._hb_payload = payload
        self._hb_thread = threading.Thread(
            target=self._heartbeat, name="dfm-event-heartbeat", daemon=True)
        self._hb_thread.start()

    def _heartbeat(self):
        while True:
            wait = self.heartbeat_s - (time.monotonic() - self._last)
            if wait > 0:
                if self._hb_stop.wait(wait):
                    return
                continue
            p = {}
            if self._hb_payload is not None:
                try:
                    p = self._hb_payload() or {}
                except Exception:
                    p = {}
            self.emit("run.alive", **p)

    def _stop_heartbeat(self):
        self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(CLOSE_TIMEOUT_S)
            self._hb_thread = None

    def emit(self, ev: str, **payload):
        if self._closed:
            return
        with self._lock:
            try:
                line = self._line(ev, payload)
            except Exception as e:
                _log.debug("event %s not serializable: %s", ev, e)
                return
            self._last = time.monotonic()
        for s in self.sinks:
            s.put(line)

    def close(self, ev: Optional[str] = None, **payload):
        """Send a last event (normally ``run.end``) with each sink's own
        ``dropped`` count, then shut the sinks down."""
        if self._closed:
            return
        self._closed = True
        self._stop_heartbeat()
        with self._lock:
            seq = self._seq
            for s in self.sinks:
                last = None
                if ev is not None:
                    self._seq = seq
                    try:
                        last = self._line(ev, dict(payload, dropped=s.dropped))
                    except Exception:
                        last = None
                s.close(last)


def _heartbeat_interval(value) -> float:
    if value is None or str(value).strip() == "":
        return HEARTBEAT_S
    try:
        v = float(value)
    except ValueError:
        return HEARTBEAT_S
    return max(v, 0.0)


def _trunc_argv(argv, max_args=64, max_chars=2048):
    out = []
    used = 0
    for a in argv[:max_args]:
        a = str(a)
        if used + len(a) > max_chars:
            out.append(a[:max(0, max_chars - used)] + "...")
            break
        out.append(a)
        used += len(a)
    return out
