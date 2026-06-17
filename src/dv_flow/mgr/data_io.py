#****************************************************************************
#* data_io.py
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
"""Script <-> Dataflow I/O contract.

This module is the single home for the *staging* (inputs the runner hands to a
subprocess) and *harvesting* (outputs a subprocess hands back) logic shared by
``ShellCallable``, ``ExecCallable``, and (eventually) ``std.Agent``.

The contract mirrors GitHub Actions: **environment variables for input** and
**append-only files for output**, with the files themselves located via
environment variables.  The on-disk filenames below are the stable contract
surface -- a script may always read/write them directly (via ``$DFM_*``) or use
the ``dfm-out`` helper CLI.

The functions here are pure with respect to the DFM graph: they only touch the
filesystem and return plain dict/list values, so they are trivially unit
testable with a fake ``mk_item``.
"""
import json
import logging
from typing import Any, Callable, Dict, List, NamedTuple, Optional
from pydantic import BaseModel, ConfigDict
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE

_log = logging.getLogger("data_io")

# Canonical on-disk filenames (relative to the task rundir).  These are part of
# the public contract and must not change without a deprecation cycle.
PARAMS_FILE  = "dfm.params.json"     # full structured params, written by runner
INPUTS_FILE  = "dfm.inputs.json"     # consumed input items, written by runner
MEMENTO_IN   = "dfm.memento.json"    # prior memento, staged for the script to read
OUTPUT_FILE  = "dfm.output.jsonl"    # data items the script emits (JSONL)
ENV_FILE     = "dfm.env"             # KEY=VALUE (+ heredoc) lines the script emits
PATH_FILE    = "dfm.path"            # one directory per line the script emits
MARKERS_FILE = "dfm.markers.jsonl"   # markers the script emits (JSONL)
MEMENTO_OUT  = "dfm.memento.out.json" # memento the script writes back


class _DuckItem(BaseModel):
    """Fallback data item used when the emitted ``type`` is not registered.

    Supports arbitrary fields and is a pydantic model so it serializes cleanly
    into ``exec.json`` via ``model_dump``.  Used for both shell-task harvest and
    ``std.Agent`` result-file items.
    """
    model_config = ConfigDict(extra="allow")

    type : Optional[str] = None
    src : Optional[str] = None
    seq : int = -1


class HarvestResult(NamedTuple):
    output : List[Any]
    env_item : Optional[Any]
    markers : List[TaskMarker]
    memento : Optional[dict]


def _scalar_to_env(value: Any) -> str:
    """Render a declared-param value for a ``DFM_PARAM_<NAME>`` env var.

    Scalars are rendered verbatim (``str(value)``); lists/maps become compact
    JSON so they round-trip through ``jq`` / ``json.loads``.  ``None`` becomes
    the empty string.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # str(True) == "True"; prefer the lowercase shell-friendly form
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def serialize_item(item: Any) -> Any:
    """Serialize one input item to a plain JSON-able value.

    Shared by ``DFM_INPUTS`` staging and ``std.Agent``'s prompt builder so the
    payload shape stays identical across both.
    """
    if hasattr(item, "model_dump"):
        return item.model_dump()
    elif hasattr(item, "dict"):
        return item.dict()
    else:
        return {k: v for k, v in item.__dict__.items() if not k.startswith("_")}


def serialize_inputs(inputs: Any) -> List[Any]:
    """Serialize a list of input items to plain JSON-able values."""
    return [serialize_item(inp) for inp in (inputs or [])]


def coerce_output_item(item: Any, rundir: str) -> Any:
    """Coerce one raw output dict into a duck-typed item.

    Applies the ``std.FileSet`` ``basedir: "."`` -> rundir convenience.
    Non-dict values pass through unchanged.  Shared with ``std.Agent`` (which
    parses a single JSON result file) so the item shape stays consistent.
    """
    if not isinstance(item, dict):
        return item
    if item.get("type") == "std.FileSet" and item.get("basedir") == ".":
        item = dict(item)
        item["basedir"] = rundir
    return _DuckItem(**item)


def stage_inputs(rundir: str, input: Any, memento: Any = None) -> Dict[str, str]:
    """Write the param/input/memento files and pre-create the output files.

    Returns the ``DFM_*`` environment additions to merge into the subprocess
    environment.  A script that ignores all of these behaves exactly as before.
    """
    import os

    env: Dict[str, str] = {}

    # 1. Full structured params -> dfm.params.json
    params = input.params
    if hasattr(params, "model_dump"):
        params_full = params.model_dump(mode="json")
    elif hasattr(params, "dict"):
        params_full = params.dict()
    else:
        params_full = {}
    params_path = os.path.join(rundir, PARAMS_FILE)
    with open(params_path, "w") as fp:
        json.dump(params_full, fp, indent=2)

    # 2. Per-declared-param scalars for DFM_PARAM_<UPPER>
    field_names = []
    if hasattr(type(params), "model_fields"):
        field_names = list(type(params).model_fields.keys())
    for name in field_names:
        value = getattr(params, name, None)
        env["DFM_PARAM_%s" % name.upper()] = _scalar_to_env(value)

    # 3. Consumed input items -> dfm.inputs.json (a JSON array)
    inputs_list = serialize_inputs(getattr(input, "inputs", []))
    inputs_path = os.path.join(rundir, INPUTS_FILE)
    with open(inputs_path, "w") as fp:
        json.dump(inputs_list, fp, indent=2)

    # 4. Prior memento -> dfm.memento.json (only when present)
    if memento is not None:
        memento_path = os.path.join(rundir, MEMENTO_IN)
        if hasattr(memento, "model_dump"):
            memento_data = memento.model_dump(mode="json")
        else:
            memento_data = memento
        with open(memento_path, "w") as fp:
            json.dump(memento_data, fp, indent=2)
        env["DFM_MEMENTO"] = memento_path

    # 5. Pre-create empty output files so a script can blindly '>>' to them
    output_path  = os.path.join(rundir, OUTPUT_FILE)
    env_path     = os.path.join(rundir, ENV_FILE)
    path_path    = os.path.join(rundir, PATH_FILE)
    markers_path = os.path.join(rundir, MARKERS_FILE)
    memento_out  = os.path.join(rundir, MEMENTO_OUT)
    for p in (output_path, env_path, path_path, markers_path):
        open(p, "w").close()

    # 6. Locating env vars
    env["DFM_RUNDIR"]      = rundir
    env["DFM_SRCDIR"]      = input.srcdir
    env["DFM_TASK_NAME"]   = input.name
    env["DFM_PARAMS"]      = params_path
    env["DFM_INPUTS"]      = inputs_path
    env["DFM_OUTPUT"]      = output_path
    env["DFM_ENV"]         = env_path
    env["DFM_PATH"]        = path_path
    env["DFM_MARKERS"]     = markers_path
    env["DFM_MEMENTO_OUT"] = memento_out

    return env


def _parse_env_file(path: str) -> Dict[str, str]:
    """Parse a GHA-style env file into a {KEY: VALUE} dict.

    Supports the plain ``KEY=VALUE`` form and the multiline heredoc form::

        KEY<<EOF
        line1
        line2
        EOF
    """
    import os

    vals: Dict[str, str] = {}
    if not os.path.exists(path):
        return vals

    with open(path, "r") as fp:
        lines = fp.read().splitlines()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        # Heredoc form: KEY<<DELIM (check before '=' since a key cannot contain '<<')
        hi = line.find("<<")
        eq = line.find("=")
        if hi != -1 and (eq == -1 or hi < eq):
            key = line[:hi].strip()
            delim = line[hi + 2:].strip()
            i += 1
            buf = []
            while i < n and lines[i] != delim:
                buf.append(lines[i])
                i += 1
            # Skip the closing delimiter line if present
            if i < n:
                i += 1
            vals[key] = "\n".join(buf)
        elif eq != -1:
            key = line[:eq].strip()
            vals[key] = line[eq + 1:]
            i += 1
        else:
            _log.warning("Ignoring malformed DFM_ENV line: %r" % line)
            i += 1

    return vals


def _parse_path_file(path: str) -> List[str]:
    """Parse a DFM_PATH file into an ordered list of directories."""
    import os

    dirs: List[str] = []
    if not os.path.exists(path):
        return dirs
    with open(path, "r") as fp:
        for line in fp.read().splitlines():
            line = line.strip()
            if line:
                dirs.append(line)
    return dirs


def harvest_outputs(
        rundir: str,
        *,
        mk_item: Callable[..., Any],
        src_name: str = None) -> HarvestResult:
    """Parse the append-only output files into graph objects.

    ``mk_item(type, **kwargs)`` is injected (typically ``ctxt.mkDataItem``) so
    this module has no dependency on the runner/ctxt classes.  When ``mk_item``
    cannot build an item (unregistered type or unexpected field) a duck-typed
    fallback is used and a warning marker is emitted so typos surface.

    Returns ``(output_items, env_item_or_None, markers, memento_or_None)``.
    """
    import os

    output: List[Any] = []
    markers: List[TaskMarker] = []
    seq = 0

    def _build(item_type, fields):
        nonlocal seq
        try:
            item = mk_item(item_type, **fields)
        except Exception as e:
            markers.append(TaskMarker(
                msg="Falling back to duck-typed item for type '%s': %s" % (item_type, e),
                severity=SeverityE.Warning))
            item = _DuckItem(type=item_type, **fields)
        # src/seq mirror how the leaf restores items (task_node_leaf.py)
        try:
            item.src = src_name
            item.seq = seq
        except Exception:
            pass
        seq += 1
        output.append(item)

    # --- DFM_OUTPUT: JSONL of typed data items -----------------------------
    output_path = os.path.join(rundir, OUTPUT_FILE)
    if os.path.exists(output_path):
        with open(output_path, "r") as fp:
            for lineno, line in enumerate(fp, start=1):
                line = line.strip()
                if line == "":
                    continue
                try:
                    item = json.loads(line)
                except Exception as e:
                    markers.append(TaskMarker(
                        msg="Malformed DFM_OUTPUT line %d: %s" % (lineno, e),
                        severity=SeverityE.Warning))
                    continue
                if not isinstance(item, dict):
                    markers.append(TaskMarker(
                        msg="DFM_OUTPUT line %d is not a JSON object" % lineno,
                        severity=SeverityE.Warning))
                    continue
                item_type = item.pop("type", None)
                if item_type is None:
                    markers.append(TaskMarker(
                        msg="DFM_OUTPUT line %d missing 'type'" % lineno,
                        severity=SeverityE.Warning))
                    continue
                # Convenience: basedir "." -> the actual rundir (mirrors agent.py)
                if item_type == "std.FileSet" and item.get("basedir") == ".":
                    item["basedir"] = rundir
                _build(item_type, item)

    # --- DFM_ENV + DFM_PATH: fold into a single std.Env item ---------------
    vals = _parse_env_file(os.path.join(rundir, ENV_FILE))
    path_dirs = _parse_path_file(os.path.join(rundir, PATH_FILE))
    env_item = None
    if vals or path_dirs:
        env_kwargs = {}
        if vals:
            env_kwargs["vals"] = vals
        if path_dirs:
            env_kwargs["prepend_path"] = {"PATH": os.pathsep.join(path_dirs)}
        try:
            env_item = mk_item("std.Env", **env_kwargs)
            try:
                env_item.src = src_name
            except Exception:
                pass
        except Exception as e:
            markers.append(TaskMarker(
                msg="Failed to build std.Env from DFM_ENV/DFM_PATH: %s" % e,
                severity=SeverityE.Warning))
            env_item = _DuckItem(type="std.Env", src=src_name, **env_kwargs)

    # --- DFM_MARKERS: JSONL of {severity,msg,loc?} -------------------------
    markers_path = os.path.join(rundir, MARKERS_FILE)
    if os.path.exists(markers_path):
        with open(markers_path, "r") as fp:
            for lineno, line in enumerate(fp, start=1):
                line = line.strip()
                if line == "":
                    continue
                try:
                    md = json.loads(line)
                except Exception as e:
                    markers.append(TaskMarker(
                        msg="Malformed DFM_MARKERS line %d: %s" % (lineno, e),
                        severity=SeverityE.Warning))
                    continue
                markers.append(coerce_marker(md))

    # --- DFM_MEMENTO_OUT: opaque script-owned blob -------------------------
    memento = None
    memento_path = os.path.join(rundir, MEMENTO_OUT)
    if os.path.exists(memento_path):
        try:
            with open(memento_path, "r") as fp:
                content = fp.read()
            if content.strip():
                memento = json.loads(content)
        except Exception as e:
            markers.append(TaskMarker(
                msg="Malformed %s: %s" % (MEMENTO_OUT, e),
                severity=SeverityE.Warning))
            memento = None

    return HarvestResult(output, env_item, markers, memento)


def coerce_marker(md: Any) -> TaskMarker:
    """Coerce a parsed marker dict into a TaskMarker.

    Coerces a string ``severity`` to ``SeverityE`` (unknown -> Info) and a
    ``loc`` dict to ``TaskMarkerLoc``.  Shared by harvest and ``std.Agent``.
    """
    if not isinstance(md, dict):
        return TaskMarker(
            msg="Invalid marker format: %s" % str(md),
            severity=SeverityE.Warning)
    try:
        data = dict(md)
        sev = data.get("severity", "info")
        if isinstance(sev, str):
            try:
                data["severity"] = SeverityE(sev)
            except ValueError:
                data["severity"] = SeverityE.Info
        loc = data.get("loc")
        if isinstance(loc, dict):
            data["loc"] = TaskMarkerLoc(**loc)
        return TaskMarker(**data)
    except Exception as e:
        return TaskMarker(
            msg="Invalid marker format (%s): %s" % (e, str(md)),
            severity=SeverityE.Warning)
