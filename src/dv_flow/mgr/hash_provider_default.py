#****************************************************************************
#* hash_provider_default.py
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
import hashlib
import os
from pathlib import Path
from .fileset import FileSet


class DefaultHashProvider:
    """Default hash provider that computes MD5 hash of file contents.
    
    This is a fallback provider that handles all file types by hashing
    the raw file contents. It has the lowest priority so specialized
    providers can override for specific file types.
    """
    
    def supports(self, filetype: str) -> bool:
        """Supports all file types (fallback provider)."""
        return True
    
    async def compute_hash(self, fileset: FileSet, rundir: str) -> str:
        """Compute MD5 hash of all files in the fileset.
        
        Args:
            fileset: The fileset to hash
            rundir: The run directory (base path for resolving relative paths)
            
        Returns:
            MD5 hash string (hex digest) of all file contents combined
        """
        hasher = hashlib.md5()
        
        # Hash the filetype itself (different types should have different hashes)
        hasher.update(fileset.filetype.encode('utf-8'))
        
        # Resolve basedir relative to rundir
        if os.path.isabs(fileset.basedir):
            basedir = Path(fileset.basedir)
        else:
            basedir = Path(rundir) / fileset.basedir
        
        # Sort files for deterministic ordering
        sorted_files = sorted(fileset.files)
        
        for file in sorted_files:
            # Hash the filename (so renamed files get different hashes)
            hasher.update(file.encode('utf-8'))
            
            # Resolve file path
            if os.path.isabs(file):
                filepath = Path(file)
            else:
                filepath = basedir / file
            
            # Hash file contents
            try:
                # Skip directories
                if filepath.is_dir():
                    hasher.update(b'<DIRECTORY>')
                    continue
                    
                with open(filepath, 'rb') as f:
                    # Read in chunks to handle large files efficiently
                    while chunk := f.read(8192):
                        hasher.update(chunk)
            except FileNotFoundError:
                # If file doesn't exist, hash a special marker
                # This ensures missing files produce a different hash
                hasher.update(b'<FILE_NOT_FOUND>')
            except IsADirectoryError:
                # Directory passed as file
                hasher.update(b'<DIRECTORY>')
        
        # Also hash other fileset properties that affect behavior
        for incdir in sorted(fileset.incdirs):
            hasher.update(b'INCDIR:')
            hasher.update(incdir.encode('utf-8'))
        
        for define in sorted(fileset.defines):
            hasher.update(b'DEFINE:')
            hasher.update(define.encode('utf-8'))
        
        # Hash params as sorted key-value pairs
        for key in sorted(fileset.params.keys()):
            hasher.update(b'PARAM:')
            hasher.update(key.encode('utf-8'))
            hasher.update(b'=')
            hasher.update(str(fileset.params[key]).encode('utf-8'))
        
        return hasher.hexdigest()
