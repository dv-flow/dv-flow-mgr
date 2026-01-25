#****************************************************************************
#* cmd_cache.py
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


class CmdCache:
    """Cache management command dispatcher"""
    
    def __call__(self, args):
        """Dispatch to the appropriate cache subcommand"""
        if hasattr(args, 'cache_func'):
            return args.cache_func(args)
        else:
            print("Error: No cache subcommand specified")
            print("Available subcommands: init")
            return 1
