#****************************************************************************
#* cmd_llms.py
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
import os
import sys


class CmdLlms(object):

    def __call__(self, args):
        llms_txt_path = self._find_llms_txt()
        
        if llms_txt_path is None:
            print("Error: llms.txt not found", file=sys.stderr)
            return 1
        
        try:
            with open(llms_txt_path, 'r') as f:
                sys.stdout.write(f.read())
            return 0
        except Exception as e:
            print(f"Error reading llms.txt: {e}", file=sys.stderr)
            return 1

    def _find_llms_txt(self):
        # First, check in the package share directory
        pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        share_path = os.path.join(pkg_dir, "share", "llms.txt")
        
        if os.path.exists(share_path):
            return share_path
        
        # If not found, search up from current directory to find project root
        current_dir = os.getcwd()
        while True:
            llms_path = os.path.join(current_dir, "llms.txt")
            if os.path.exists(llms_path):
                return llms_path
            
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                break
            current_dir = parent
        
        return None
