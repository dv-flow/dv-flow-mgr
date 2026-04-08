import asyncio
import dataclasses as dc
import logging
import os
from typing import ClassVar, List
from .task_data import TaskDataResult
from .exec_callable import _merge_env_filesets
from .naming_scheme import TaskNamingContext

@dc.dataclass
class ShellCallable(object):
    body : str
    srcdir : str
    shell : str
    _log : ClassVar = logging.getLogger("ShellCallable")

    def _get_filenames(self, ctxt, input):
        """Get log and script filenames using the naming scheme if available."""
        naming = getattr(ctxt.ctxt, 'naming_scheme', None) if ctxt.ctxt else None
        if naming is not None:
            root_pkg = getattr(ctxt.ctxt, 'root_package_name', "")
            fq_name = input.name
            leaf = fq_name.rsplit(".", 1)[-1] if "." in fq_name else fq_name
            inherits = getattr(input, 'inherits_rundir', False)
            ctx = TaskNamingContext(
                fq_name=fq_name,
                leaf_name=leaf,
                package_name="",
                root_package_name=root_pkg,
                inherits_rundir=inherits,
            )
            return naming.log_filename(ctx), naming.script_filename(ctx)
        return "%s.log" % input.name, "%s_cmd.sh" % input.name

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

        log_fname, script_fname = self._get_filenames(ctxt, input)

        if cmd.find("\n") != -1:
            # This is an inline command. Create a script
            # file so env vars are expanded
            cmd_f = os.path.join(input.rundir, script_fname)
            with open(cmd_f, "w") as fp:
                fp.write("#!/bin/%s\n" % (self.shell if self.shell != "shell" else "bash"))
                fp.write(cmd)
            os.chmod(cmd_f, 0o755)

        # Use ctxt.exec() to respect jobserver token management
        logfile = os.path.join(input.rundir, log_fname)
        
        if cmd.find("\n") != -1:
            # Multi-line command - already created script file above
            cmd_script = os.path.join(input.rundir, script_fname)
            status = await ctxt.exec([shell, cmd_script], logfile=logfile, env=env, cwd=input.rundir)
        else:
            # Single-line command - use shell -c
            status = await ctxt.exec([shell, "-c", cmd], logfile=logfile, env=env, cwd=input.rundir)

        return TaskDataResult(
            status=status
        )
