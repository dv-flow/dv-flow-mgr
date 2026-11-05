#****************************************************************************
#* cache_util.py
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
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from .cache_provider import CacheEntry, CompressionType
from .param_ref_eval import ParamRefEval
from .fileset import FileSet
from .hash_provider import collect_incdirs, compute_hash


_log = logging.getLogger(__name__)


async def compute_cache_key(
    task_name: str,
    task_def,
    params: Any,
    inputs: List[Any],
    rundir: str,
    hash_registry
) -> Optional[str]:
    """Compute cache key for a task.
    
    Args:
        task_name: Name of the task
        task_def: Task definition with cache configuration
        params: Task parameters
        inputs: Task input filesets
        rundir: Run directory
        hash_registry: ExtRgy with hash providers
        
    Returns:
        Cache key in format 'taskname:hash', or None if task is not cacheable
    """
    # Check if task has caching enabled
    # Caching is opt-in: must be explicitly enabled via cache config
    if task_def is None:
        # No taskdef - disable caching
        cache_enabled = False
        cache_config = None
    elif not hasattr(task_def, 'cache'):
        # No cache attribute - disable caching
        cache_enabled = False
        cache_config = None
    elif task_def.cache is None:
        # Cache explicitly set to None - disable caching
        cache_enabled = False
        cache_config = None
    elif isinstance(task_def.cache, bool):
        # Cache is a boolean
        cache_enabled = task_def.cache
        cache_config = None
    else:
        # Cache is a CacheDef object
        cache_enabled = task_def.cache.enabled
        cache_config = task_def.cache
    
    if not cache_enabled:
        return None
    
    # Start building hash
    hasher = hashlib.md5()
    
    # Hash task name
    hasher.update(task_name.encode('utf-8'))
    
    # Include search path the consuming task will compile against -- the union
    # over all its input filesets, not each fileset's own incdirs (see
    # hash_provider.collect_incdirs)
    incdirs = collect_incdirs(inputs, rundir)

    # Hash input filesets
    for input_item in inputs:
        if isinstance(input_item, FileSet):
            # Get hash provider for this filetype
            provider = hash_registry.get_hash_provider(input_item.filetype)
            if provider:
                fileset_hash = await compute_hash(provider, input_item, rundir, incdirs)
                hasher.update(fileset_hash.encode('utf-8'))
            else:
                _log.warning(f"No hash provider for filetype {input_item.filetype}, skipping")
    
    # Hash parameters (as JSON for deterministic ordering)
    if params:
        if hasattr(params, 'model_dump'):
            params_dict = params.model_dump()
        elif hasattr(params, '__dict__'):
            params_dict = params.__dict__
        else:
            params_dict = params
        
        try:
            params_json = json.dumps(params_dict, sort_keys=True, default=str)
            hasher.update(params_json.encode('utf-8'))
        except Exception as e:
            _log.warning(f"Failed to serialize params for cache key: {e}")
            # If we can't serialize params, task is not cacheable
            return None
    
    # Hash extra cache.hash expressions
    if cache_config and cache_config.hash:
        expr_eval = ParamRefEval()
        # TODO: Set up proper variable resolution context
        
        for hash_expr in cache_config.hash:
            try:
                result = expr_eval.eval(hash_expr)
                hasher.update(str(result).encode('utf-8'))
            except Exception as e:
                _log.warning(f"Failed to evaluate cache hash expression '{hash_expr}': {e}")
                # If we can't evaluate hash expression, task is not cacheable
                return None
    
    hash_value = hasher.hexdigest()
    return f"{task_name}:{hash_value}"


async def check_cache(
    cache_key: str,
    cache_providers: List
) -> Optional[CacheEntry]:
    """Check if cache entry exists in any provider.
    
    Args:
        cache_key: Cache key to look up
        cache_providers: List of cache providers to check
        
    Returns:
        CacheEntry if found, None otherwise
    """
    for provider in cache_providers:
        try:
            entry = await provider.get(cache_key)
            if entry:
                _log.info(f"Cache hit for {cache_key}")
                return entry
        except Exception as e:
            _log.warning(f"Error checking cache provider: {e}")
            continue
    
    _log.debug(f"Cache miss for {cache_key}")
    return None


async def store_in_cache(
    cache_key: str,
    output_template: Dict[str, Any],
    artifacts_dir: Optional[Path],
    cache_providers: List,
    compression: CompressionType = CompressionType.No,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Store task result in cache.
    
    Args:
        cache_key: Cache key
        output_template: Output data with ${{ rundir }} placeholders
        artifacts_dir: Directory containing task artifacts (or None)
        cache_providers: List of cache providers
        compression: Compression type
        metadata: Optional metadata dict
        
    Returns:
        True if stored in at least one provider, False otherwise
    """
    from datetime import datetime
    
    stored_count = 0
    
    for provider in cache_providers:
        if not provider.writable:
            continue
        
        try:
            # Store artifacts first if present
            if artifacts_dir and artifacts_dir.exists():
                await provider.store_artifacts(cache_key, artifacts_dir, compression)
            
            # Create cache entry
            entry = CacheEntry(
                key=cache_key,
                output_template=output_template,
                artifacts_path="artifacts" if compression == CompressionType.No else f"artifacts.tar.{'gz' if compression in [CompressionType.Yes, CompressionType.Gzip] else 'bz2'}",
                compression=compression,
                created=datetime.now(),
                metadata=metadata or {}
            )
            
            # Store entry
            if await provider.put(cache_key, entry):
                stored_count += 1
                _log.info(f"Stored {cache_key} in cache")
        except Exception as e:
            _log.warning(f"Failed to store in cache provider: {e}")
            continue
    
    return stored_count > 0


def _rel_to_rundir(path, rundir: str) -> Optional[str]:
    """Return ``path`` relative to ``rundir`` (as a POSIX string), or None if
    it is outside. The rundir may be a symlink (e.g. into a rundir store), and
    tools may report either the logical or the resolved form of a path, so
    both forms of each are tried."""
    p = Path(path)
    if not p.is_absolute():
        return None
    logical = Path(os.path.abspath(rundir))
    real = Path(os.path.realpath(rundir))
    for cand, base in ((Path(os.path.abspath(p)), logical),
                       (Path(os.path.realpath(p)), real),
                       (Path(os.path.abspath(p)), real)):
        try:
            return cand.relative_to(base).as_posix()
        except ValueError:
            continue
    return None


def validate_output_paths(output: List[Any], rundir: str) -> bool:
    """Validate that all output filesets reference paths within rundir.
    
    Args:
        output: List of output items
        rundir: Run directory path (logical; may be a symlink)
        
    Returns:
        True if all filesets are within rundir, False otherwise
    """
    for item in output:
        if isinstance(item, FileSet):
            # Check basedir
            basedir = Path(item.basedir)
            if basedir.is_absolute() and _rel_to_rundir(basedir, rundir) is None:
                _log.warning(
                    f"Fileset basedir {basedir} is outside rundir {rundir}, "
                    "task not cacheable"
                )
                return False
    
    return True


def convert_output_to_template(output: List[Any], rundir: str) -> Dict[str, Any]:
    """Convert task output to cache template with ${{ rundir }} placeholders.
    
    Args:
        output: List of output items
        rundir: Run directory path (logical; may be a symlink)
        
    Returns:
        Output template dict
    """
    template_output = []
    
    for item in output:
        if hasattr(item, 'model_dump'):
            item_dict = item.model_dump()
            
            # Replace rundir paths with placeholder
            if isinstance(item, FileSet):
                basedir = Path(item_dict['basedir'])
                if basedir.is_absolute():
                    rel_path = _rel_to_rundir(basedir, rundir)
                    if rel_path is not None:
                        item_dict['basedir'] = f"${{{{ rundir }}}}/{rel_path}"
                    # else: path is outside rundir, keep as-is
            
            template_output.append(item_dict)
        else:
            template_output.append(item)
    
    return {'output': template_output}
