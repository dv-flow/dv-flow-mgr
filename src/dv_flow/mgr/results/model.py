#****************************************************************************
#* model.py -- the results.json (dvflow-results/1) models
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
"""Pydantic models of the on-disk run record, ``results.json``.

These models are the source of the JSON Schema
(``share/dvflow-results.schema.json``, ``dfm util schema --results``).
``ResultNode`` allows extra fields, so profile fields (``testname``,
``seed``, hdlsim's ``errors`` ...) survive a round trip.
"""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_ID = "dvflow-results/1"

Status = Literal["pass", "fail", "error", "timeout", "skip", "notrun"]
CheckStatus = Literal["pass", "fail", "error", "skip"]
Severity = Literal["info", "warning", "error", "fatal"]
Better = Literal["higher", "lower", "none"]


class Loc(BaseModel):
    """Where to look: a file, and optionally a line and column."""
    model_config = ConfigDict(extra="allow")
    path: str = ""
    line: Optional[int] = None
    pos: Optional[int] = None


class Diagnostic(BaseModel):
    """A message worth showing (the TaskMarker shape plus DV fields)."""
    model_config = ConfigDict(extra="allow")
    severity: Severity = "error"
    msg: str = ""
    category: Optional[str] = None
    loc: Optional[Loc] = None
    src_loc: Optional[Loc] = None
    time: Optional[str] = None
    hier: Optional[str] = None


class Metric(BaseModel):
    """A number with a unit and a direction for run-to-run compares."""
    model_config = ConfigDict(extra="allow")
    value: float
    unit: str = ""
    better: Better = "none"
    label: Optional[str] = None


class Check(BaseModel):
    """A named success criterion. ``value`` is the observed metric value."""
    model_config = ConfigDict(extra="allow")
    name: str
    status: CheckStatus
    metric: Optional[str] = None
    op: Optional[str] = None
    goal: Optional[Any] = None
    value: Optional[float] = None
    msg: Optional[str] = None


class Stamp(BaseModel):
    """A file's mtime and size when the run ended (staleness detection)."""
    path: str
    mtime: Optional[float] = None
    size: Optional[int] = None
    # Set by readers (``dfm show results``), never written by the recorder:
    # ok | stale | missing
    state: Optional[Literal["ok", "stale", "missing"]] = None


class Artifact(BaseModel):
    """A ``std.FileSet`` dump plus its ``role``/``label`` and file stamps."""
    model_config = ConfigDict(extra="allow")
    type: str = "std.FileSet"
    filetype: str = ""
    basedir: str = ""
    files: List[str] = Field(default_factory=list)
    attributes: List[str] = Field(default_factory=list)
    role: str = "other"
    label: Optional[str] = None
    stamps: List[Stamp] = Field(default_factory=list)
    # Set by readers when any stamp is stale or missing.
    stale: Optional[bool] = None


class ResultNode(BaseModel):
    """One verdict node. ``types`` is its is-a lineage, most-derived first."""
    model_config = ConfigDict(extra="allow")
    name: str = ""
    type: str = "std.Result"
    types: List[str] = Field(default_factory=lambda: ["std.Result"])
    status: Status
    passed: bool = False
    msg: str = ""
    task: Optional[str] = None
    rundir: Optional[str] = None
    tool: Dict[str, Any] = Field(default_factory=dict)
    attrs: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Metric] = Field(default_factory=dict)
    checks: List[Check] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
    diagnostics: List[Diagnostic] = Field(default_factory=list)
    artifacts: List[Artifact] = Field(default_factory=list)
    children: List["ResultNode"] = Field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reused: bool = False


class RunInfo(BaseModel):
    """What was run, where and when, and how it exited."""
    model_config = ConfigDict(extra="allow")
    id: str
    root: Union[str, List[str]] = ""
    argv: List[str] = Field(default_factory=list)
    cwd: str = ""
    rundir: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    exit_status: int = 0
    host: str = ""
    dfm_version: str = ""


class LogRef(BaseModel):
    path: str
    line: Optional[int] = None


class FailureEntry(BaseModel):
    """A non-passing leaf (or TaskResult), ready for triage."""
    model_config = ConfigDict(extra="allow")
    path: str
    status: Status
    msg: str = ""
    type: str = "std.Result"
    task: Optional[str] = None
    checks: List[Check] = Field(default_factory=list)
    log: Optional[LogRef] = None
    waves: Optional[str] = None


class Summary(BaseModel):
    """The part of the record an agent or CI step reads (computed the same
    way for every domain)."""
    model_config = ConfigDict(extra="allow")
    status: Status
    msg: str = ""
    counts: Dict[str, int] = Field(default_factory=dict)
    metrics: Dict[str, Metric] = Field(default_factory=dict)
    failures: List[FailureEntry] = Field(default_factory=list)


class ResultsFile(BaseModel):
    """``rundir/out/<run-id>/results.json``."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    schema_: Literal["dvflow-results/1"] = Field(SCHEMA_ID, alias="schema")
    run: RunInfo
    summary: Summary
    result: ResultNode

    def dump(self) -> Dict[str, Any]:
        """The on-disk form: no nulls, and no empty containers or
        ``reused: false`` in nodes, so an agent can read the file whole."""
        d = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        _prune_node(d["result"])
        for f in d["summary"].get("failures", []):
            if not f.get("checks"):
                f.pop("checks", None)
        return d


_PRUNE = ("tool", "attrs", "metrics", "checks", "counts", "diagnostics",
          "artifacts", "children")


def _prune_node(n):
    for k in _PRUNE:
        if k in n and not n[k]:
            del n[k]
    if n.get("reused") is False:
        del n["reused"]
    for c in n.get("children", []):
        _prune_node(c)


ResultNode.model_rebuild()


SCHEMA_URL = "https://dv-flow.github.io/dvflow-results.schema.json"


def results_json_schema():
    """The JSON Schema of ``results.json`` (``share/dvflow-results.schema.json``)."""
    s = ResultsFile.model_json_schema(by_alias=True)
    ret = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_URL,
        "title": "DV Flow run results",
        "description": "rundir/out/<run-id>/results.json, written at the end of every dfm run",
    }
    ret.update({k: v for k, v in s.items() if k not in ("title", "description")})
    # `schema` has a default in the model (so writers needn't pass it), but a
    # file without it is not a results record.
    req = ret.setdefault("required", [])
    if "schema" not in req:
        req.insert(0, "schema")
    return ret
