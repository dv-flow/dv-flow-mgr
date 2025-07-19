import dataclasses as dc
import importlib
import importlib.util
import logging
import os
import sys
from typing import ClassVar, List
from .task_data import TaskDataResult

@dc.dataclass
class ExecCallable(object):
    body : str
    srcdir : str
    shell: str = "pytask"
    _log : ClassVar = logging.getLogger("ExecCallable")

    async def __call__(self, ctxt, input):
        self._log.debug("--> ExecCallable")
        self._log.debug("Body:\n%s" % self.body)

        # If it is a single line, then we have a spec to load
        # Otherwise, we have an inline task

        if self.body.find("\n") == -1:
            # Two forms:
            # <path>::method
            # <method-path>

            ci = self.body.find("::")
            if ci != -1:
                # have a file to load
                file = self.body[:ci]
                method = self.body[ci+2:]
                if not os.path.isabs(file):
                    file = os.path.join(input.srcdir, file)

                spec = importlib.util.spec_from_file_location(input.name, file)
                module = importlib.util.module_from_spec(spec)
                sys.modules[input.name] = module
                spec.loader.exec_module(module)

                callable = getattr(module, method)
                pass
            else:
            #     self._log.debug("Use PyTask implementation")
                last_dot = self.body.rfind('.')
                clsname = self.body[last_dot+1:]
                modname = self.body[:last_dot]

                try:
                    if modname not in sys.modules:
                        if input.srcdir not in sys.path:
                           sys.path.append(input.srcdir)
                        mod = importlib.import_module(modname)
                    else:
                        mod = sys.modules[modname]
                except ModuleNotFoundError as e:
                    raise Exception("Failed to import module %s: %s" % (modname, str(e)))
                
                if not hasattr(mod, clsname):
                    raise Exception("Method %s not found in module %s" % (clsname, modname))
                callable = getattr(mod, clsname)
        else:
            text_lines = self.body.splitlines()

            least_whitespace = 2^32
            have_content = False
            for line in text_lines:
                line_no_leading_ws = line.lstrip()
                if line_no_leading_ws != "":
                    have_content = True
                    leading_ws = len(line) - len(line_no_leading_ws)
                    if leading_ws < least_whitespace:
                        least_whitespace = leading_ws
            # Remove leading whitespace
            if have_content:
                for i,line in enumerate(text_lines):
                    if len(line) >= least_whitespace:
                        text_lines[i] = line[least_whitespace:]

            method = "async def pytask(ctxt, input):\n" + "\n".join(["    %s" % l for l in text_lines])

            exec(method)

            callable = locals()['pytask']

        result = await callable(ctxt, input)

        if result is None:
            result = TaskDataResult()

        self._log.debug("<-- ExecCallable")
        return result
