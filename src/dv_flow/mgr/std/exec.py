#****************************************************************************
#* exec.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import asyncio
import os
import logging
from pydantic import BaseModel
from dv_flow.mgr import TaskDataResult, TaskMarker

_log = logging.getLogger("Exec")

class Memento(BaseModel):
    timestamp_file : str
    timestamp : float

async def Exec(runner, input) -> TaskDataResult:
    _log.debug("TaskExec run: %s: cmd=%s" % (input.name, input.params.command))

    # Running the command is gated by inputs to the task
    need_to_run = input.params.when == "always" or input.changed

    status = 0
    markers = []

    if need_to_run:
        fp = open(os.path.join(input.rundir, "run.log"), "w")
        fp.write("Command: %s\n" % input.params.command)
        proc = await asyncio.create_subprocess_shell(
            input.params.command,
            stdout=fp,
            stderr=asyncio.subprocess.STDOUT)

        result = await proc.wait()

        status = proc.returncode

        if status != 0:
            markers.append(TaskMarker(
                message="Command \"%s\" failed with status %d" % (
                    input.params.command, status), severity="error"))

    changed = False
    ex_memento = input.memento
    memento = None

    if ex_memento is not None and status == 0:
        ex_memento_o = None
        try:
            ex_memento_o = Memento(**ex_memento)
        except Exception as e:
            _log.debug("Failed to deserialize memento: %s" % str(e))

        if ex_memento_o is not None:
            if input.params.timestamp is not None and input.params.timestamp != "":
                # Have a file to use
                if os.path.isfile(os.path.join(input.rundir, input.params.timestamp)):
                    ts_file = os.path.join(input.rundir, input.params.timestamp)
                    ts = os.path.getmtime(ts_file)

                    if ts_file != ex_memento_o.timestamp_file or ts != ex_memento_o.timestamp:
                        changed = True

                    memento = Memento(timestamp_file=ts_file, timestamp=ts)
                else:
                    markers.append(TaskMarker(
                        message="Timestamp file %s not found" % (
                            os.path.join(input.rundir, input.params.timestamp)),
                        severity="error"))
                    status = 1
            else:
                memento = Memento()
        else:
            changed = True
        memento = ex_memento
    else:
        # No existing memento, or the task failed
        changed = (status == 0)

    if input.params.when == "changed":
        changed = input.changed

    if input.params.timestamp is not None and input.params.timestamp != "":
        # Check the timestamp file
        try:
            with open(input.params.timestamp_file, "r") as f:
                timestamp = float(f.read())
        except FileNotFoundError:
            timestamp = 0.0

        if timestamp < input.params.timestamp:
            changed = True

    

    return TaskDataResult(
        status=status,
        changed=changed,
        markers=markers,
        memento=memento)


