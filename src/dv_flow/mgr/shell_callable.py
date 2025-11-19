import asyncio
import dataclasses as dc
import logging
import os
from typing import ClassVar, List
from .task_data import TaskDataResult

@dc.dataclass
class ShellCallable(object):
    body : str
    srcdir : str
    shell : str
    _log : ClassVar = logging.getLogger("ShellCallable")

    async def __call__(self, ctxt, input):

        shell = ("/bin/%s" % self.shell) if self.shell != "shell" else "bash"
        # Setup environment for the call
        env = ctxt.env.copy()
        # Merge std.Env data items from inputs
        # Collect all std.Env vals in dependency order, oldest first
        env_items = []
        for item in getattr(input, "inputs", []):
            if getattr(item, "type", None) == "std.Env" and hasattr(item, "vals") and isinstance(item.vals, dict):
                env_items.append(item.vals)
        # Merge all keys from all std.Env, oldest first, newest override
        merged_env = {}
        for vals in env_items:
            for k, v in vals.items():
                merged_env[k] = v
        env.update(merged_env)
        env["TASK_SRCDIR"] = input.srcdir
        env["TASK_RUNDIR"] = input.rundir
#        env["TASK_PARAMS"] = input.params.dumpto_json()

        cmd = self.body

        # if self.body.find("\n") != -1:
        #     # This is an inline command. Create a script
        #     # file so env vars are expanded
        #     cmd = os.path.join(input.rundir, "%s_cmd.sh" % input.name)
        #     with open(cmd, "w") as fp:
        #         fp.write("#!/bin/%s\n" % (self.shell if self.shell != "shell" else "bash"))
        #         fp.write(self.body)
        #     os.chmod(cmd, 0o755)

        fp = open(os.path.join(input.rundir, "%s.log" % input.name), "w")

        proc = await asyncio.create_subprocess_shell(
            cmd,
            executable=shell,
            env=env,
            cwd=input.rundir,
            stdout=fp,
            stderr=asyncio.subprocess.STDOUT)
        
        status = await proc.wait()
        
        fp.close()

        return TaskDataResult(
            status=status
        )
