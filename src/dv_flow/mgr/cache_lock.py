#****************************************************************************
#* cache_lock.py
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
import asyncio
import fcntl
import os
import time
from pathlib import Path
from typing import Optional


class FileLock:
    """File-based lock for cache access control.
    
    Supports both shared (read) and exclusive (write) locks using fcntl.
    Works on both local and NFS file systems (NFS v4+ required for proper locking).
    """
    
    def __init__(self, lock_file: Path, shared: bool = False, timeout: int = 30):
        """Initialize file lock.
        
        Args:
            lock_file: Path to lock file
            shared: If True, acquire shared lock (allows multiple readers).
                   If False, acquire exclusive lock (single writer).
            timeout: Maximum time in seconds to wait for lock acquisition
        """
        self.lock_file = Path(lock_file)
        self.shared = shared
        self.timeout = timeout
        self.fd: Optional[int] = None
    
    async def __aenter__(self):
        """Acquire lock with timeout."""
        # Ensure parent directory exists
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Open lock file
        self.fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o666)
        
        # Determine lock mode
        lock_mode = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
        
        # Try to acquire lock with timeout
        start_time = time.time()
        while True:
            try:
                # Non-blocking lock attempt
                fcntl.flock(self.fd, lock_mode | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                # Lock is held by another process
                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    # Close file descriptor and raise timeout error
                    os.close(self.fd)
                    self.fd = None
                    raise TimeoutError(
                        f"Failed to acquire {'shared' if self.shared else 'exclusive'} "
                        f"lock on {self.lock_file} within {self.timeout} seconds"
                    )
                
                # Wait a bit before retrying
                await asyncio.sleep(0.1)
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock."""
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except Exception:
                # Best effort cleanup - ignore errors during release
                pass
            finally:
                self.fd = None
        
        # Don't suppress exceptions
        return False
    
    def __del__(self):
        """Cleanup in case lock wasn't properly released."""
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
