#****************************************************************************
#* cache_provider.py
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
import enum
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Union
from pydantic import BaseModel, Field


class CompressionType(enum.Enum):
    """Compression types for cache artifacts"""
    No = "no"           # No compression (default)
    Yes = "yes"         # Use system default compression (gzip)
    Gzip = "gzip"       # Explicit gzip
    Bzip2 = "bzip2"     # Explicit bzip2


class CacheEntry(BaseModel):
    """Entry stored in cache.
    
    Contains task output template and artifacts that can be restored
    to recreate the task's output without re-execution.
    """
    key: str
    """Cache key in format taskname:hash"""
    
    output_template: Dict[str, Any]
    """Task output data with ${{ rundir }} placeholders for paths"""
    
    artifacts_path: Optional[str] = None
    """Path to artifacts directory or archive (relative to cache entry dir)"""
    
    compression: CompressionType = CompressionType.No
    """Compression type used for artifacts"""
    
    created: datetime = Field(default_factory=datetime.now)
    """When this cache entry was created"""
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    """Additional metadata (e.g., machine, user, dfm version)"""


class CacheProvider(Protocol):
    """Protocol for cache storage backends.
    
    Cache providers implement different storage mechanisms for cached task results.
    Examples: local directory, shared NFS cache, remote object storage, etc.
    """
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve cached entry by key.
        
        Args:
            key: Cache key in format taskname:hash
            
        Returns:
            CacheEntry if found, None otherwise
        """
        ...
    
    async def put(self, key: str, entry: CacheEntry) -> bool:
        """Store entry in cache.
        
        Args:
            key: Cache key in format taskname:hash
            entry: Cache entry to store
            
        Returns:
            True if successfully stored, False otherwise
        """
        ...
    
    async def exists(self, key: str) -> bool:
        """Check if entry exists in cache.
        
        Args:
            key: Cache key in format taskname:hash
            
        Returns:
            True if entry exists, False otherwise
        """
        ...
