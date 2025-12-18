#****************************************************************************
#* uptodate_callable.py
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
import dataclasses as dc
import importlib
import importlib.util
import logging
import os
import sys
from typing import ClassVar
from .uptodate_ctxt import UpToDateCtxt

@dc.dataclass
class UpToDateCallable(object):
    """Callable factory for custom up-to-date check methods"""
    body : str
    srcdir : str
    _log : ClassVar = logging.getLogger("UpToDateCallable")

    async def __call__(self, ctxt: UpToDateCtxt) -> bool:
        """
        Invoke the custom up-to-date check method.
        Returns True if the task is up-to-date, False otherwise.
        """
        self._log.debug("--> UpToDateCallable: %s" % self.body)

        # Two forms:
        # <path>::method
        # <method-path>

        ci = self.body.find("::")
        if ci != -1:
            # have a file to load
            file = self.body[:ci]
            method = self.body[ci+2:]
            if not os.path.isabs(file):
                file = os.path.join(self.srcdir, file)

            spec = importlib.util.spec_from_file_location("uptodate_check", file)
            module = importlib.util.module_from_spec(spec)
            sys.modules["uptodate_check"] = module
            spec.loader.exec_module(module)

            callable = getattr(module, method)
        else:
            last_dot = self.body.rfind('.')
            clsname = self.body[last_dot+1:]
            modname = self.body[:last_dot]

            try:
                if modname not in sys.modules:
                    if self.srcdir not in sys.path:
                        sys.path.append(self.srcdir)
                    mod = importlib.import_module(modname)
                else:
                    mod = sys.modules[modname]
            except ModuleNotFoundError as e:
                raise Exception("Failed to import module %s: %s" % (modname, str(e)))
            
            if not hasattr(mod, clsname):
                raise Exception("Method %s not found in module %s" % (clsname, modname))
            callable = getattr(mod, clsname)

        result = await callable(ctxt)

        self._log.debug("<-- UpToDateCallable: %s" % result)
        return result
