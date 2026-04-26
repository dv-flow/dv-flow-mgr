#****************************************************************************
#* lsf_job.py
#*
#* LSF job helpers: build bsub commands, parse bjobs output, bkill.
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
import os
import re
import subprocess
from typing import List, Optional, Tuple

from .runner_backend import ResourceReq
from .runner_config import LsfConfig


_log = logging.getLogger("LsfJob")


def _memory_to_mb(memory: str) -> int:
    """Convert memory string (e.g. '4G', '512M') to megabytes."""
    m = re.match(r'^(\d+)\s*([gGmMkKtT]?)$', memory.strip())
    if not m:
        _log.warning("Cannot parse memory '%s', assuming MB", memory)
        try:
            return int(memory)
        except ValueError:
            return 1024
    val = int(m.group(1))
    unit = m.group(2).upper()
    if unit == 'G':
        return val * 1024
    elif unit == 'T':
        return val * 1024 * 1024
    elif unit == 'K':
        return max(1, val // 1024)
    else:  # M or empty
        return val


def build_bsub_cmd(
    resource_req: ResourceReq,
    config: LsfConfig,
    worker_cmd: List[str],
    resource_class: str = "",
    log_dir: Optional[str] = None,
) -> List[str]:
    """Assemble the full bsub command line.

    Uses bsub_cmd from config (not hardcoded 'bsub').
    Accumulates resource_select from config into -R "select[...]".
    """
    cmd = [config.bsub_cmd]

    # Cores
    if resource_req.cores > 0:
        cmd.extend(["-n", str(resource_req.cores)])

    # Memory
    if resource_req.memory:
        cmd.extend(["-M", resource_req.memory])

    # Queue
    queue = resource_req.queue or config.queue
    if queue:
        cmd.extend(["-q", queue])

    # Project
    project = resource_req.project or config.project
    if project:
        cmd.extend(["-P", project])

    # rusage for memory reservation
    mem_mb = _memory_to_mb(resource_req.memory)
    cmd.extend(["-R", "rusage[mem=%d]" % mem_mb])

    # select predicates (accumulated from config + resource_req)
    all_select = list(resource_req.resource_select)
    if all_select:
        select_str = " && ".join(all_select)
        cmd.extend(["-R", "select[%s]" % select_str])

    # Direct worker stdout/stderr to log files
    if log_dir:
        import uuid as _uuid
        worker_id = _uuid.uuid4().hex[:8]
        cmd.extend(["-oo", os.path.join(log_dir, "lsf_worker_%s.log" % worker_id)])
        cmd.extend(["-eo", os.path.join(log_dir, "lsf_worker_%s.err" % worker_id)])

    # Extra bsub flags
    cmd.extend(config.bsub_extra)

    # Separator and worker command as individual args
    cmd.append("--")
    cmd.extend(worker_cmd)
    if resource_class:
        cmd.extend(["--resource-class", resource_class])

    return cmd


def bsub_submit(cmd_args: List[str]) -> str:
    """Submit a job via bsub and return the job ID.

    Parses the bsub stdout for the job ID in the format:
        Job <12345> is submitted to queue <queuename>.
    """
    _log.info("Submitting: %s", " ".join(cmd_args))
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("bsub failed (rc=%d): %s" % (result.returncode, result.stderr))

    # Parse job ID
    m = re.search(r'Job <(\d+)>', result.stdout)
    if not m:
        raise RuntimeError("Cannot parse job ID from bsub output: %s" % result.stdout)

    job_id = m.group(1)
    _log.info("Submitted job %s", job_id)
    return job_id


def bjobs_query(job_id: str, bjobs_cmd: str = "bjobs") -> str:
    """Query job status via bjobs.

    Returns one of: 'PEND', 'RUN', 'DONE', 'EXIT', 'UNKNOWN', or other LSF states.
    Uses -o for explicit output format to avoid parsing ambiguity.
    """
    cmd = [bjobs_cmd, "-o", "stat", "-noheader", job_id]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _log.warning("bjobs failed for %s: %s", job_id, result.stderr)
        return "UNKNOWN"

    status = result.stdout.strip().split('\n')[0].strip()
    return status if status else "UNKNOWN"


def bkill(job_id: str, bkill_cmd: str = "bkill") -> bool:
    """Kill a job via bkill. Returns True if successful."""
    cmd = [bkill_cmd, job_id]
    _log.info("Killing job %s", job_id)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _log.warning("bkill failed for %s: %s", job_id, result.stderr)
        return False
    return True
