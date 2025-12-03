import asyncio
import dataclasses as dc
import logging
import os
from typing import ClassVar, List
from .task_data import TaskDataResult
from .exec_callable import _merge_env_filesets

@dc.dataclass
class ShellCallable(object):
    body : str
    srcdir : str
    shell : str
    _log : ClassVar = logging.getLogger("ShellCallable")

    async def __call__(self, ctxt, input):

        shell = ("/bin/%s" % self.shell) if self.shell != "shell" else "bash"
        # Setup environment for the call, merging any std.Env items
        env = _merge_env_filesets(ctxt, input)
        env["TASK_SRCDIR"] = input.srcdir
        env["TASK_RUNDIR"] = input.rundir
#        env["TASK_PARAMS"] = input.params.dumpto_json()

        # Expand parameter references in the body (e.g., ${{ this.p1 }}, ${{ p2 }}, ${{ rundir }})
        def _resolve_token(tok: str):
            tok = tok.strip()
            if tok == 'rundir':
                return input.rundir
            # Allow direct param access (e.g., p2)
            if hasattr(input.params, tok):
                return getattr(input.params, tok)
            # Allow 'this.<param>' access
            if tok.startswith('this.'):
                attr = tok.split('.', 1)[1]
                if hasattr(input.params, attr):
                    return getattr(input.params, attr)
            # Fallback: leave as-is
            return '${{ %s }}' % tok
        import re
        def _expand(s: str):
            return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", lambda m: str(_resolve_token(m.group(1))), s)
        cmd = _expand(self.body)

        self._log.debug("Shell command: %s" % cmd)
        self._log.debug("self.body: %s" % self.body)

        if cmd.find("\n") != -1:
            # This is an inline command. Create a script
            # file so env vars are expanded
            cmd_f = os.path.join(input.rundir, "%s_cmd.sh" % input.name)
            with open(cmd_f, "w") as fp:
                fp.write("#!/bin/%s\n" % (self.shell if self.shell != "shell" else "bash"))
                fp.write(cmd)
            os.chmod(cmd_f, 0o755)

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
