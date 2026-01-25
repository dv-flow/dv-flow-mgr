#****************************************************************************
#* hash_provider.py
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
from typing import Protocol
from .fileset import FileSet


class HashProvider(Protocol):
    """Protocol for hash providers that compute hashes for filesets.
    
    Hash providers are pluggable components that determine how to hash
    different file types. For example, a specialized provider for SystemVerilog
    files might hash not just the source files but also included files.
    """
    
    def supports(self, filetype: str) -> bool:
        """Check if this provider handles the given filetype.
        
        Args:
            filetype: The filetype string (e.g., 'systemVerilogSource', 'cSource')
            
        Returns:
            True if this provider can hash this filetype
        """
        ...
    
    async def compute_hash(self, fileset: FileSet, rundir: str) -> str:
        """Compute hash for the given fileset.
        
        Args:
            fileset: The fileset to hash
            rundir: The run directory (base path for resolving relative paths)
            
        Returns:
            MD5 hash string (hex digest)
        """
        ...
