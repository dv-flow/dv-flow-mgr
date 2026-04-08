#****************************************************************************
#* resource_resolver.py
#*
#* Resolves resource requirements from task tags and runner config.
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
from typing import Any, Dict, List, Optional

from .runner_backend import ResourceReq
from .runner_config import RunnerConfig


_log = logging.getLogger("ResourceResolver")


def _parse_walltime(walltime_str: str) -> int:
    """Convert HH:MM walltime string to minutes."""
    if not walltime_str:
        return 60
    parts = walltime_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except ValueError:
        _log.warning("Invalid walltime format '%s', using default 60 minutes", walltime_str)
    return 60


def _extract_resource_tag(tags: List[Any]) -> Optional[Dict[str, Any]]:
    """Extract ResourceTag fields from a task's tags list.

    Tags can be strings ("std.ResourceTag") or dicts
    ({"std.ResourceTag": {"cores": 4}}).
    Returns the parameter dict if found, None otherwise.
    """
    if not tags:
        return None
    for tag in tags:
        if isinstance(tag, str) and tag == "std.ResourceTag":
            return {}
        elif isinstance(tag, dict):
            if "std.ResourceTag" in tag:
                val = tag["std.ResourceTag"]
                return val if isinstance(val, dict) else {}
    return None


def resolve_resources(
    tags: List[Any],
    config: RunnerConfig,
) -> ResourceReq:
    """Resolve resource requirements from task tags and config.

    Resolution order:
    1. Check for resource_class on the task's ResourceTag. If set,
       look up the named class in config.
    2. Otherwise, use explicit cores/memory/queue from the tag.
    3. Fall back to runner config defaults.

    The project field always comes from LsfConfig (not from the tag).
    """
    tag_data = _extract_resource_tag(tags)

    # Start with config defaults
    cores = config.defaults.cores
    memory = config.defaults.memory
    walltime_minutes = _parse_walltime(config.defaults.walltime)
    queue = config.lsf.queue
    resource_select = list(config.lsf.resource_select)

    if tag_data is not None:
        resource_class_name = tag_data.get("resource_class", "")

        if resource_class_name and resource_class_name in config.resource_classes:
            # Resolve from resource class definition
            rc = config.resource_classes[resource_class_name]
            cores = rc.cores
            memory = rc.memory
            if rc.queue:
                queue = rc.queue
            if rc.resource_select:
                resource_select = resource_select + rc.resource_select
        elif resource_class_name and resource_class_name not in config.resource_classes:
            raise ValueError(
                "Unknown resource class '%s'. Available classes: %s"
                % (resource_class_name, ", ".join(config.resource_classes.keys()) or "(none)")
            )
        else:
            # Use explicit values from tag
            if "cores" in tag_data:
                cores = int(tag_data["cores"])
            if "memory" in tag_data:
                memory = tag_data["memory"]
            if "queue" in tag_data:
                queue = tag_data["queue"]

        if "walltime" in tag_data:
            walltime_minutes = _parse_walltime(tag_data["walltime"])

    return ResourceReq(
        cores=cores,
        memory=memory,
        queue=queue,
        walltime_minutes=walltime_minutes,
        project=config.lsf.project,
        resource_select=resource_select,
    )
