#****************************************************************************
#* task_exec_serialize.py
#*
#* Serialize/deserialize tasks for remote execution.
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
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
import logging
import sys
from typing import Any, Dict, List, Optional

from .runner_backend import ResourceReq, TaskExecRequest
from .resource_resolver import resolve_resources
from .runner_config import RunnerConfig
from .task_data import TaskDataResult


_log = logging.getLogger("TaskExecSerialize")


def _get_callable_spec(task_node) -> str:
    """Extract the callable spec (e.g. 'dv_flow.mgr.std.fileset.FileSet').

    For pytask, the spec lives in taskdef.run (the flow.dv 'run:' field).
    Falls back to reading ExecCallable.body if taskdef is unavailable.
    """
    taskdef = getattr(task_node, "taskdef", None)
    if taskdef is not None:
        run = getattr(taskdef, "run", None)
        if run:
            return run

    # Fallback: read from the callable wrapper's body
    task_callable = getattr(task_node, "task", None)
    if task_callable is not None:
        body = getattr(task_callable, "body", None)
        if body and "\n" not in body:
            return body
    return ""


def _get_shell(task_node) -> str:
    """Determine the shell type for a task node."""
    taskdef = getattr(task_node, "taskdef", None)
    if taskdef is not None:
        shell = getattr(taskdef, "shell", None)
        if shell:
            return shell
    return "pytask"


def _get_body(task_node) -> Optional[str]:
    """Extract inline shell/pytask body from the callable wrapper.

    For shell tasks the body is the script text.
    For inline pytask the body is the Python source.
    NOT the taskdef.body (which is a list of sub-task defs).
    """
    task_callable = getattr(task_node, "task", None)
    if task_callable is not None:
        body = getattr(task_callable, "body", None)
        if body:
            return body
    return None


def _get_tags(task_node) -> List[Any]:
    """Extract tags from a task node's taskdef."""
    taskdef = getattr(task_node, "taskdef", None)
    if taskdef is not None:
        return getattr(taskdef, "tags", [])
    return []


def serialize_task(
    task_node,
    runner_config: RunnerConfig,
    env: Optional[Dict[str, str]] = None,
) -> TaskExecRequest:
    """Serialize a TaskNodeLeaf into a TaskExecRequest for remote execution.

    The request carries:
    - callable_spec: dotted Python path to the function/class to call
    - shell: "pytask" for Python callables, "bash"/etc for shell scripts
    - body: inline script text (shell) or callable spec (pytask)
    - params: dict of task parameters (JSON-serializable)
    - inputs: list of serialized input data items
    - pythonpath: sys.path entries the worker needs to import the callable
    """
    # Serialize params via pydantic model_dump
    params = {}
    if task_node.params is not None:
        if hasattr(task_node.params, "model_dump"):
            params = task_node.params.model_dump(mode="json")
        elif isinstance(task_node.params, dict):
            params = task_node.params

    # Serialize inputs from upstream tasks
    inputs = []
    in_params = getattr(task_node, "in_params", None) or []
    for item in in_params:
        if hasattr(item, "model_dump"):
            inputs.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            inputs.append(item)

    # Build pythonpath
    pythonpath = []
    if task_node.srcdir and task_node.srcdir not in pythonpath:
        pythonpath.append(task_node.srcdir)
    for p in sys.path:
        if p and p not in pythonpath:
            pythonpath.append(p)

    # Resolve resource requirements from tags
    tags = _get_tags(task_node)
    resource_req = resolve_resources(tags, runner_config)

    # Memento from previous run
    memento = None
    if task_node.result is not None and task_node.result.memento is not None:
        if hasattr(task_node.result.memento, "model_dump"):
            memento = task_node.result.memento.model_dump(mode="json")
        else:
            memento = task_node.result.memento

    rundir = task_node.rundir
    if isinstance(rundir, list):
        rundir = "/".join(rundir)

    return TaskExecRequest(
        name=task_node.name,
        callable_spec=_get_callable_spec(task_node),
        shell=_get_shell(task_node),
        body=_get_body(task_node),
        srcdir=task_node.srcdir,
        rundir=rundir,
        pythonpath=pythonpath,
        params=params,
        inputs=inputs,
        env=env or {},
        memento=memento,
        resource_req=resource_req,
    )


def deserialize_result(
    data: Dict[str, Any],
    runner=None,
) -> TaskDataResult:
    """Deserialize a task result from a worker response.

    Args:
        data: Dict from JSON with status, changed, output, markers, memento
        runner: TaskSetRunner for mkDataItem reconstruction (optional)

    Returns:
        TaskDataResult with reconstructed output items
    """
    status = data.get("status", 0)
    changed = data.get("changed", False)
    memento = data.get("memento")

    from .task_data import TaskMarker, SeverityE
    markers = []
    for m_data in data.get("markers", []):
        markers.append(TaskMarker(
            msg=m_data.get("msg", ""),
            severity=SeverityE(m_data.get("severity", "info")),
        ))

    output = []
    for item_data in data.get("output", []):
        if runner is not None and hasattr(runner, "mkDataItem"):
            item_type = item_data.get("type", "std.FileSet")
            excluded = ("type", "src", "seq", "name", "params")
            try:
                item = runner.mkDataItem(
                    item_type,
                    **{k: v for k, v in item_data.items() if k not in excluded}
                )
                item.src = item_data.get("src", "")
                item.seq = item_data.get("seq", 0)
                output.append(item)
            except Exception as e:
                _log.warning("Failed to reconstruct output item: %s", e)
        else:
            output.append(item_data)

    return TaskDataResult(
        status=status,
        changed=changed,
        output=output,
        markers=markers,
        memento=memento,
    )
