#****************************************************************************
#* jobserver.py
#*
#* GNU Make-compatible jobserver implementation using named FIFO
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
"""
GNU Make Jobserver Implementation

This module implements the GNU Make POSIX jobserver protocol using named FIFOs.
The jobserver coordinates process execution across multiple DFM instances and
is compatible with GNU Make, CMake, and other build systems.

Protocol: https://www.gnu.org/software/make/manual/html_node/POSIX-Jobserver.html
"""

import asyncio
import atexit
import logging
import os
import re
import signal
import tempfile
import uuid
from typing import Optional

_log = logging.getLogger("JobServer")


class JobServer:
    """
    GNU Make-compatible jobserver using named FIFO.
    
    The jobserver manages a pool of "tokens" representing available processor slots.
    Tasks acquire a token before spawning a subprocess and release it when done.
    This ensures system-wide process limits are respected.
    
    Usage:
        # As root (create jobserver)
        js = JobServer(nproc=4)
        env['MAKEFLAGS'] = js.get_makeflags()
        
        # In child (detect from environment)
        js = JobServer.from_environment()
        if js:
            await js.acquire()
            # ... run subprocess ...
            js.release()
    """
    
    def __init__(self, nproc: int, fifo_path: Optional[str] = None):
        """
        Initialize jobserver with nproc total slots.
        
        Creates named FIFO and writes nproc tokens.
        
        Args:
            nproc: Total number of parallel process slots
            fifo_path: Optional custom FIFO path (auto-generated if None)
        """
        if nproc < 1:
            raise ValueError(f"nproc must be >= 1, got {nproc}")
        
        self.nproc = nproc
        self.fifo_path = fifo_path or self._generate_fifo_path()
        self._fifo_fd: Optional[int] = None
        self._acquired_count = 0
        self._enabled = True
        self._is_owner = True  # We created this jobserver
        self._closed = False
        self._acquire_queue = asyncio.Queue()  # Queue for pending acquire requests
        self._reader_task = None  # Background task reading from FIFO
        
        # Create the FIFO
        try:
            os.mkfifo(self.fifo_path, 0o600)
            _log.debug(f"Created jobserver FIFO at {self.fifo_path}")
        except FileExistsError:
            _log.warning(f"FIFO already exists at {self.fifo_path}, reusing")
        except OSError as e:
            _log.error(f"Failed to create FIFO: {e}")
            raise
        
        # Open FIFO in read/write mode (non-blocking)
        # O_RDWR prevents blocking on open (no need for separate reader/writer)
        try:
            self._fifo_fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
            _log.debug(f"Opened FIFO fd={self._fifo_fd}")
        except OSError as e:
            _log.error(f"Failed to open FIFO: {e}")
            os.unlink(self.fifo_path)
            raise
        
        # Write nproc tokens to the FIFO
        # Note: Unlike GNU Make, DFM writes N tokens (not N-1) because
        # DFM doesn't hold an "implicit token" - each exec() call represents
        # an independent subprocess that needs a token.
        tokens_to_write = nproc
        if tokens_to_write > 0:
            token_data = b'T' * tokens_to_write
            try:
                written = os.write(self._fifo_fd, token_data)
                if written != tokens_to_write:
                    _log.warning(f"Wrote {written} tokens, expected {tokens_to_write}")
                _log.debug(f"Wrote {written} tokens to jobserver")
            except OSError as e:
                _log.error(f"Failed to write tokens: {e}")
                self.close()
                raise
        
        # Register cleanup handlers
        atexit.register(self._cleanup)
        self._setup_signal_handlers()
        
        _log.info(f"JobServer created: nproc={nproc}, fifo={self.fifo_path}")
    
    @staticmethod
    def from_environment() -> Optional['JobServer']:
        """
        Detect and connect to existing jobserver from MAKEFLAGS environment variable.
        
        Parses MAKEFLAGS for --jobserver-auth=fifo:/path format.
        
        Returns:
            JobServer instance if found, None otherwise
        """
        makeflags = os.environ.get('MAKEFLAGS', '')
        if not makeflags:
            return None
        
        # Parse --jobserver-auth=fifo:/path
        match = re.search(r'--jobserver-auth=fifo:([^\s]+)', makeflags)
        if not match:
            _log.debug("No jobserver found in MAKEFLAGS")
            return None
        
        fifo_path = match.group(1)
        
        # Verify FIFO exists
        if not os.path.exists(fifo_path):
            _log.warning(f"Jobserver FIFO not found: {fifo_path}")
            return None
        
        # Create a non-owner jobserver instance
        js = object.__new__(JobServer)
        js.fifo_path = fifo_path
        js._acquired_count = 0
        js._enabled = True
        js._is_owner = False  # We don't own this jobserver
        js._closed = False
        js.nproc = -1  # Unknown (inherited)
        js._acquire_queue = asyncio.Queue()
        js._reader_task = None
        
        # Open existing FIFO
        try:
            js._fifo_fd = os.open(fifo_path, os.O_RDWR | os.O_NONBLOCK)
            _log.info(f"Connected to existing jobserver: {fifo_path}")
        except OSError as e:
            _log.warning(f"Failed to open jobserver FIFO: {e}")
            return None
        
        return js
    
    def get_makeflags(self) -> str:
        """
        Return MAKEFLAGS value for child processes.
        
        Format: --jobserver-auth=fifo:/path/to/pipe
        
        Returns:
            MAKEFLAGS string to pass to subprocesses
        """
        return f"--jobserver-auth=fifo:{self.fifo_path}"
    
    async def acquire(self, timeout: float = 60.0):
        """
        Acquire a job token (async, blocks if none available).
        
        Uses a queue to manage multiple concurrent acquire requests.
        A single background task reads tokens from the FIFO and distributes them.
        
        Args:
            timeout: Maximum time to wait in seconds (default 60)
            
        Raises:
            asyncio.TimeoutError: If timeout expires
            RuntimeError: If jobserver is disabled or closed
        """
        if not self._enabled:
            _log.debug("Jobserver disabled, skipping acquire")
            return
        
        if self._closed:
            raise RuntimeError("JobServer is closed")
        
        if self._fifo_fd is None:
            raise RuntimeError("JobServer FIFO not open")
        
        # Start the background reader task if not already running
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._read_tokens_loop())
        
        _log.debug("Acquiring job token...")
        
        # Create a future for this acquire request
        future = asyncio.Future()
        await self._acquire_queue.put(future)
        
        try:
            # Wait for token with timeout
            await asyncio.wait_for(future, timeout=timeout)
            self._acquired_count += 1
            _log.debug(f"Acquired token (count={self._acquired_count})")
        except asyncio.TimeoutError:
            # Timeout - cancel the request if still pending
            if not future.done():
                future.cancel()
            _log.warning(f"Jobserver acquire timeout after {timeout}s")
            raise
        except Exception as e:
            _log.error(f"Error during acquire: {e}")
            raise
    
    async def _read_tokens_loop(self):
        """
        Background task that reads tokens from FIFO and distributes to waiting acquirers.
        """
        loop = asyncio.get_event_loop()
        
        def token_ready():
            """Called when FIFO has data available to read"""
            # Check if closed before attempting to read
            if self._closed or self._fifo_fd is None:
                return
                
            try:
                # Read 1 byte (1 token)
                token = os.read(self._fifo_fd, 1)
                if len(token) == 1:
                    # Token available - give it to next waiter
                    if not self._acquire_queue.empty():
                        future = self._acquire_queue.get_nowait()
                        if not future.done():
                            future.set_result(None)
                    else:
                        # No one waiting - write token back
                        # This can happen during cleanup when tokens are being returned
                        try:
                            if self._fifo_fd is not None and not self._closed:
                                os.write(self._fifo_fd, b'T')
                        except (OSError, TypeError):
                            pass  # FD closed or invalid, ignore
                else:
                    # EOF or error
                    _log.warning("Token read returned empty, jobserver may be closed")
            except BlockingIOError:
                # No data available yet, will be called again
                pass
            except (OSError, TypeError) as e:
                # FD closed or invalid
                if not self._closed:
                    _log.error(f"Error reading token: {e}")
        
        # Register callback for when data is available
        if self._fifo_fd is not None:
            loop.add_reader(self._fifo_fd, token_ready)
        
        try:
            # Run until jobserver is closed
            while not self._closed:
                await asyncio.sleep(0.1)
        finally:
            # Only remove reader if FD is still valid
            if self._fifo_fd is not None:
                try:
                    loop.remove_reader(self._fifo_fd)
                except (ValueError, OSError):
                    # FD already closed or invalid, ignore
                    pass
    
    def release(self):
        """
        Release a job token back to the pool.
        
        Always releases tokens even if jobserver is disabled, to prevent deadlock.
        """
        if self._closed:
            _log.warning("Attempted to release token from closed jobserver")
            return
        
        if self._acquired_count <= 0:
            _log.warning("Attempted to release token when none are held")
            return
        
        if self._fifo_fd is None:
            _log.error("Cannot release token: FIFO not open")
            return
        
        try:
            # Write 1 byte back to FIFO
            written = os.write(self._fifo_fd, b'T')
            if written == 1:
                self._acquired_count -= 1
                _log.info(f"Released token (count={self._acquired_count})")
            else:
                _log.warning(f"Token release wrote {written} bytes, expected 1")
        except OSError as e:
            _log.error(f"Error releasing token: {e}")
            # Don't fail the task, but log the issue
    
    def close(self):
        """
        Close jobserver and cleanup resources.
        
        If we own the jobserver, removes the FIFO file.
        Returns all acquired tokens before closing.
        """
        if self._closed:
            return
        
        _log.debug(f"Closing jobserver (owner={self._is_owner}, acquired={self._acquired_count})")
        
        # Mark as closed first to stop the reader loop
        self._closed = True
        
        # Remove the reader callback before closing FD
        if self._fifo_fd is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.remove_reader(self._fifo_fd)
            except (ValueError, OSError, RuntimeError):
                # FD already removed, invalid, or no event loop - ignore
                pass
        
        # Cancel background reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        
        # Return all acquired tokens
        if self._acquired_count > 0 and self._fifo_fd is not None:
            _log.debug(f"Returning {self._acquired_count} tokens before close")
            try:
                tokens = b'T' * self._acquired_count
                os.write(self._fifo_fd, tokens)
            except OSError as e:
                _log.warning(f"Failed to return tokens on close: {e}")
            self._acquired_count = 0
        
        # Close file descriptor
        if self._fifo_fd is not None:
            try:
                os.close(self._fifo_fd)
                _log.debug("Closed FIFO fd")
            except OSError as e:
                _log.warning(f"Error closing FIFO fd: {e}")
            self._fifo_fd = None
        
        # Remove FIFO file if we own it
        if self._is_owner and os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
                _log.debug(f"Removed FIFO: {self.fifo_path}")
            except OSError as e:
                _log.warning(f"Failed to remove FIFO: {e}")
    
    def _cleanup(self):
        """Cleanup handler for atexit"""
        if not self._closed:
            _log.debug("JobServer cleanup via atexit")
            self.close()
    
    def _signal_handler(self, signum, frame):
        """Signal handler for graceful shutdown"""
        _log.debug(f"JobServer received signal {signum}")
        self.close()
        # Re-raise as SystemExit
        raise SystemExit(128 + signum)
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for cleanup"""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (OSError, ValueError) as e:
            # Signal handlers may not work in all contexts (e.g., threads)
            _log.debug(f"Could not setup signal handlers: {e}")
    
    @staticmethod
    def _generate_fifo_path() -> str:
        """Generate a unique FIFO path in temp directory"""
        tmpdir = os.environ.get('TMPDIR') or tempfile.gettempdir()
        pid = os.getpid()
        uid = uuid.uuid4().hex[:8]
        return os.path.join(tmpdir, f'dfm-jobserver-{pid}-{uid}.fifo')
    
    def __repr__(self):
        return f"JobServer(nproc={self.nproc}, fifo={self.fifo_path}, acquired={self._acquired_count})"
