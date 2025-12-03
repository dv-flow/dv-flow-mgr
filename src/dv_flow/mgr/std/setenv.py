import os
import glob
import logging
import pydantic.dataclasses as dc
from typing import Dict, List, Tuple
from pydantic import BaseModel
from dv_flow.mgr import TaskDataInput, TaskRunCtxt, TaskDataResult

_log = logging.getLogger("SetEnv")

class SetEnvMemento(BaseModel):
    """
    Captures the last-evaluated mapping of environment variables to values.
    Used to determine whether the task output has changed.
    """
    vals: List[Tuple[str, str]] = dc.Field(default_factory=list)
    append_path: List[Tuple[str, str]] = dc.Field(default_factory=list)
    prepend_path: List[Tuple[str, str]] = dc.Field(default_factory=list)

def _is_glob_pattern(val: str) -> bool:
    return any(c in val for c in ['*','?','['])

async def SetEnv(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """
    Expands environment variable specifications and produces a std.Env data item.
    - For each entry (name -> value) in 'setenv':
      * If value contains glob metacharacters, expand relative to srcdir (unless absolute)
      * Multiple matches are joined with os.pathsep
      * Matches are converted to absolute paths and sorted for determinism
      * If no matches, the original pattern is retained (treated as literal)
      * Non-glob values are passed through unchanged
    Change detection compares the resolved mapping against the previous memento.
    """
    # Retrieve the parameter value. Depending on how map-typed params are
    # processed, we may receive either:
    # - a plain dict
    # - a ParamDef instance whose 'value' holds the dict
    params_obj = getattr(input.params, "setenv", None)

    if params_obj is None:
        env = ctxt.mkDataItem("std.Env")
        return TaskDataResult(
            changed=True,
            output=[env],
            memento=SetEnvMemento()
        )

    _log.debug("SetEnv: raw params_obj type=%s repr=%s", type(params_obj), repr(params_obj))

    if isinstance(params_obj, dict):
        # Map param typically yields dict of ParamDef entries
        params_map = {}
        for k, v in params_obj.items():
            _log.debug("SetEnv: params_obj dict entry %s type=%s repr=%s", k, type(v), repr(v))
            if hasattr(v, "value"):
                params_map[k] = getattr(v, "value")
            else:
                params_map[k] = v

    _log.debug("SetEnv: final params_map=%s", params_map)

    # Extract append/prepend path maps if present
    append_map = {}
    append_obj = getattr(input.params, "append_path", None)
    if isinstance(append_obj, dict):
        for k, v in append_obj.items():
            if hasattr(v, "value"):
                append_map[k] = getattr(v, "value")
            else:
                append_map[k] = v

    prepend_map = {}
    prepend_obj = getattr(input.params, "prepend_path", None)
    if isinstance(prepend_obj, dict):
        for k, v in prepend_obj.items():
            if hasattr(v, "value"):
                prepend_map[k] = getattr(v, "value")
            else:
                prepend_map[k] = v

    _log.debug("SetEnv: append_map(raw)=%s", append_map)
    _log.debug("SetEnv: prepend_map(raw)=%s", prepend_map)

    resolved = {}

    resolved = {}
    for k, v in params_map.items():
        if isinstance(v, str) and _is_glob_pattern(v):
            pattern = v if os.path.isabs(v) else os.path.join(input.srcdir, v)
            matches = glob.glob(pattern)
            if matches:
                matches = sorted(map(lambda p: os.path.abspath(p), matches))
                if len(matches) == 1:
                    resolved_v = matches[0]
                else:
                    resolved_v = os.pathsep.join(matches)
            else:
                resolved_v = v
        else:
            resolved_v = v
        resolved[k] = resolved_v

    append_resolved = {}
    for k, v in append_map.items():
        if isinstance(v, str) and _is_glob_pattern(v):
            pattern = v if os.path.isabs(v) else os.path.join(input.srcdir, v)
            matches = glob.glob(pattern)
            if matches:
                matches = sorted(map(lambda p: os.path.abspath(p), matches))
                if len(matches) == 1:
                    resolved_v = matches[0]
                else:
                    resolved_v = os.pathsep.join(matches)
            else:
                resolved_v = v
        else:
            resolved_v = v
        append_resolved[k] = resolved_v

    prepend_resolved = {}
    for k, v in prepend_map.items():
        if isinstance(v, str) and _is_glob_pattern(v):
            pattern = v if os.path.isabs(v) else os.path.join(input.srcdir, v)
            matches = glob.glob(pattern)
            if matches:
                matches = sorted(map(lambda p: os.path.abspath(p), matches))
                if len(matches) == 1:
                    resolved_v = matches[0]
                else:
                    resolved_v = os.pathsep.join(matches)
            else:
                resolved_v = v
        else:
            resolved_v = v
        prepend_resolved[k] = resolved_v

    # Build memento (sorted list of tuples for deterministic comparison)
    memento = SetEnvMemento(
        vals=sorted(resolved.items(), key=lambda x: x[0]),
        append_path=sorted(append_resolved.items(), key=lambda x: x[0]),
        prepend_path=sorted(prepend_resolved.items(), key=lambda x: x[0]),
    )

    # Load previous memento if available
    changed = True
    if input.memento is not None:
        try:
            ex_memento = SetEnvMemento(**input.memento)
            changed = (
                ex_memento.vals != memento.vals or
                ex_memento.append_path != memento.append_path or
                ex_memento.prepend_path != memento.prepend_path or
                input.changed
            )
        except Exception as e:
            _log.warning("Failed to load previous memento: %s", str(e))
            changed = True

    env = ctxt.mkDataItem("std.Env")
    env.vals = resolved
    if hasattr(env, "append_path"):
        env.append_path = append_resolved
    if hasattr(env, "prepend_path"):
        env.prepend_path = prepend_resolved

    _log.debug(
        "SetEnv(%s) changed=%s vals=%s append_path=%s prepend_path=%s",
        input.name,
        changed,
        resolved,
        append_resolved,
        prepend_resolved,
    )

    return TaskDataResult(
        changed=changed,
        output=[env],
        memento=memento
    )
