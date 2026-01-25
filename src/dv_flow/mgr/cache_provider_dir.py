#****************************************************************************
#* cache_provider_dir.py
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
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from .cache_provider import CacheEntry, CompressionType
from .cache_lock import FileLock


class DirectoryCacheProvider:
    """Cache provider that stores entries in a directory structure.
    
    Structure:
        <cachedir>/
            <taskname>/
                <hash>/
                    .lock          - Lock file for concurrent access
                    output.json    - Output template
                    metadata.json  - Cache metadata
                    artifacts/     - Uncompressed artifacts (if no compression)
                    artifacts.tar.gz - Compressed artifacts (if compression enabled)
    """
    
    def __init__(self, cache_dir: Path, writable: bool = True):
        """Initialize directory cache provider.
        
        Args:
            cache_dir: Root directory for cache storage
            writable: Whether this cache is writable
        """
        self.cache_dir = Path(cache_dir)
        self.writable = writable
        
        # Create cache directory if writable
        if self.writable:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_entry_dir(self, key: str) -> Path:
        """Get directory for cache entry.
        
        Args:
            key: Cache key in format taskname:hash
            
        Returns:
            Path to entry directory
        """
        # Split key into taskname and hash
        parts = key.split(':', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid cache key format: {key}. Expected 'taskname:hash'")
        
        taskname, hash_value = parts
        return self.cache_dir / taskname / hash_value
    
    async def exists(self, key: str) -> bool:
        """Check if entry exists in cache."""
        entry_dir = self._get_entry_dir(key)
        output_file = entry_dir / "output.json"
        return output_file.exists()
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve cached entry by key."""
        entry_dir = self._get_entry_dir(key)
        output_file = entry_dir / "output.json"
        metadata_file = entry_dir / "metadata.json"
        lock_file = entry_dir / ".lock"
        
        if not output_file.exists():
            return None
        
        # Acquire shared lock for reading
        async with FileLock(lock_file, shared=True, timeout=30):
            # Read output template
            with open(output_file, 'r') as f:
                output_data = json.load(f)
            
            # Read metadata
            metadata = {}
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            # Determine artifacts path and compression
            artifacts_path = None
            compression = CompressionType.No
            
            if (entry_dir / "artifacts").exists():
                artifacts_path = "artifacts"
                compression = CompressionType.No
            elif (entry_dir / "artifacts.tar.gz").exists():
                artifacts_path = "artifacts.tar.gz"
                compression = CompressionType.Gzip
            elif (entry_dir / "artifacts.tar.bz2").exists():
                artifacts_path = "artifacts.tar.bz2"
                compression = CompressionType.Bzip2
            
            # Create CacheEntry
            entry = CacheEntry(
                key=key,
                output_template=output_data['output_template'],
                artifacts_path=artifacts_path,
                compression=compression,
                created=metadata.get('created', output_data.get('created')),
                metadata=metadata
            )
            
            return entry
    
    async def put(self, key: str, entry: CacheEntry) -> bool:
        """Store entry in cache."""
        if not self.writable:
            return False
        
        entry_dir = self._get_entry_dir(key)
        output_file = entry_dir / "output.json"
        metadata_file = entry_dir / "metadata.json"
        lock_file = entry_dir / ".lock"
        
        # Create entry directory
        entry_dir.mkdir(parents=True, exist_ok=True)
        
        # Acquire exclusive lock for writing
        async with FileLock(lock_file, shared=False, timeout=30):
            # Write output template
            output_data = {
                'output_template': entry.output_template,
                'created': entry.created.isoformat() if entry.created else None
            }
            
            # Use atomic write: write to temp file, then rename
            temp_output = output_file.with_suffix('.tmp')
            with open(temp_output, 'w') as f:
                json.dump(output_data, f, indent=2)
            temp_output.rename(output_file)
            
            # Write metadata
            temp_metadata = metadata_file.with_suffix('.tmp')
            with open(temp_metadata, 'w') as f:
                json.dump(entry.metadata, f, indent=2)
            temp_metadata.rename(metadata_file)
            
            # Artifacts should already be in place at this point
            # (caller is responsible for placing artifacts in entry_dir)
        
        return True
    
    async def extract_artifacts(self, entry: CacheEntry, target_dir: Path, 
                               use_symlinks: bool = False) -> bool:
        """Extract artifacts from cache to target directory.
        
        Args:
            entry: Cache entry containing artifacts
            target_dir: Directory to extract artifacts to
            use_symlinks: If True, use symlinks instead of copying (faster)
            
        Returns:
            True if successful, False otherwise
        """
        if not entry.artifacts_path:
            return True  # No artifacts to extract
        
        entry_dir = self._get_entry_dir(entry.key)
        artifacts_source = entry_dir / entry.artifacts_path
        
        if not artifacts_source.exists():
            return False
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Acquire shared lock for reading
        lock_file = entry_dir / ".lock"
        async with FileLock(lock_file, shared=True, timeout=30):
            if entry.compression == CompressionType.No:
                # Uncompressed directory - copy or symlink
                if use_symlinks:
                    # Create symlinks for each file
                    for item in artifacts_source.rglob('*'):
                        if item.is_file():
                            rel_path = item.relative_to(artifacts_source)
                            target_path = target_dir / rel_path
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            if target_path.exists():
                                target_path.unlink()
                            target_path.symlink_to(item)
                else:
                    # Copy entire directory
                    if artifacts_source.is_dir():
                        shutil.copytree(artifacts_source, target_dir, dirs_exist_ok=True)
            else:
                # Compressed archive - extract using tar
                compression_flag = 'z' if entry.compression == CompressionType.Gzip else 'j'
                
                # Run tar extraction
                proc = await asyncio.create_subprocess_exec(
                    'tar', f'-x{compression_flag}f', str(artifacts_source),
                    '-C', str(target_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    raise Exception(
                        f"Failed to extract artifacts: {stderr.decode('utf-8')}"
                    )
        
        return True
    
    async def store_artifacts(self, key: str, artifacts_dir: Path, 
                            compression: CompressionType = CompressionType.No) -> bool:
        """Store artifacts directory in cache.
        
        Args:
            key: Cache key
            artifacts_dir: Directory containing artifacts to store
            compression: Compression type to use
            
        Returns:
            True if successful, False otherwise
        """
        if not self.writable:
            return False
        
        entry_dir = self._get_entry_dir(key)
        entry_dir.mkdir(parents=True, exist_ok=True)
        
        lock_file = entry_dir / ".lock"
        
        # Acquire exclusive lock for writing
        async with FileLock(lock_file, shared=False, timeout=30):
            if compression == CompressionType.No:
                # Copy directory without compression
                target_dir = entry_dir / "artifacts"
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(artifacts_dir, target_dir)
            else:
                # Compress using tar
                if compression == CompressionType.Gzip or compression == CompressionType.Yes:
                    archive_name = "artifacts.tar.gz"
                    compression_flag = 'z'
                else:  # Bzip2
                    archive_name = "artifacts.tar.bz2"
                    compression_flag = 'j'
                
                archive_path = entry_dir / archive_name
                
                # Run tar compression
                proc = await asyncio.create_subprocess_exec(
                    'tar', f'-c{compression_flag}f', str(archive_path),
                    '-C', str(artifacts_dir.parent),
                    artifacts_dir.name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    raise Exception(
                        f"Failed to compress artifacts: {stderr.decode('utf-8')}"
                    )
        
        return True
