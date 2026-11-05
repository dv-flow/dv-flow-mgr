#****************************************************************************
#* cmd_store.py
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
import sys


class CmdStore:
    """Rundir store command dispatcher"""

    def __call__(self, args):
        if getattr(args, 'store_func', None) is None:
            print("Error: No store subcommand specified", file=sys.stderr)
            print("Available subcommands: info, init, list, stats, candidates, "
                  "gc, migrate, unlink, relink", file=sys.stderr)
            return 1
        from ..rundir_store import RundirError
        try:
            return args.store_func(args)
        except RundirError as e:
            print("Error: %s" % e, file=sys.stderr)
            return 1
