#****************************************************************************
#* hash_provider_sv.py
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
"""
SystemVerilog hash provider that handles include files.

Uses svdep native library to discover all included files and compute
a hash that includes both root sources and all included files.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from .fileset import FileSet


_log = logging.getLogger(__name__)


class SVHashProvider:
    """Hash provider for SystemVerilog files that handles includes.
    
    This provider uses the svdep library to:
    1. Discover all `include directives in root SV files
    2. Recursively follow includes to find all dependencies
    3. Compute MD5 hash of all root + included file contents
    
    The hash does NOT include:
    - Resolved include paths (only filenames)
    - Include directory paths
    
    This ensures the hash is portable across different environments.
    """
    
    SUPPORTED_TYPES = {
        'systemVerilogSource',
        'verilogSource', 
        'systemVerilogInclude',
        'verilogInclude'
    }
    
    def supports(self, filetype: str) -> bool:
        """Check if this provider handles the given filetype."""
        return filetype in self.SUPPORTED_TYPES
    
    async def compute_hash(self, fileset: FileSet, rundir: str) -> str:
        """Compute hash for SystemVerilog fileset including all includes.
        
        Args:
            fileset: FileSet containing SV files
            rundir: Run directory (used for relative path resolution)
            
        Returns:
            MD5 hash string (32 hex characters)
        """
        try:
            # Import svdep
            import svdep.native as svdep
            
            # Get absolute paths to files
            basedir = Path(fileset.basedir)
            if not basedir.is_absolute():
                basedir = Path(rundir) / basedir
            
            files = []
            for f in fileset.files:
                file_path = Path(f)
                if not file_path.is_absolute():
                    file_path = basedir / file_path
                files.append(str(file_path.resolve()))
            
            # Get include directories
            incdirs = []
            if hasattr(fileset, 'incdirs') and fileset.incdirs:
                for incdir in fileset.incdirs:
                    inc_path = Path(incdir)
                    if not inc_path.is_absolute():
                        inc_path = Path(rundir) / inc_path
                    incdirs.append(str(inc_path.resolve()))
            
            # Compute hash using svdep (uses native if available, else pure-Python)
            hash_value = svdep.compute_hash_for_files(files, incdirs)
            
            if hash_value is None:
                _log.warning("svdep hash computation failed, falling back to default")
                return await self._fallback_hash(fileset, rundir)
            
            _log.debug(f"SVHashProvider computed hash for {len(files)} files: {hash_value[:8]}...")
            return hash_value
            
        except ImportError:
            _log.warning("svdep module not available, falling back to default hash")
            return await self._fallback_hash(fileset, rundir)
        except Exception as e:
            _log.warning(f"SVHashProvider error: {e}, falling back to default hash")
            return await self._fallback_hash(fileset, rundir)
    
    async def _fallback_hash(self, fileset: FileSet, rundir: str) -> str:
        """Fallback to default content-based hashing if svdep not available."""
        from .hash_provider_default import DefaultHashProvider
        provider = DefaultHashProvider()
        return await provider.compute_hash(fileset, rundir)
