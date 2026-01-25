#****************************************************************************
#* cache_config.py
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
import yaml
from pathlib import Path
from typing import List
from .cache_provider_dir import DirectoryCacheProvider


def load_cache_providers() -> List:
    """Load cache providers from DV_FLOW_CACHE environment variable.
    
    Returns:
        List of cache provider instances (empty list if caching not configured)
    """
    cache_env = os.environ.get('DV_FLOW_CACHE', '')
    
    if not cache_env:
        return []
    
    cache_path = Path(cache_env)
    
    # If path doesn't exist, return empty list (caching disabled)
    if not cache_path.exists():
        # If it's a path intended to be a directory, try to create it
        if not '.' in cache_path.name or cache_path.suffix in ['', '.d', '.cache']:
            # Looks like a directory path, create it
            cache_path.mkdir(parents=True, exist_ok=True)
            return [DirectoryCacheProvider(cache_path, writable=True)]
        else:
            # Looks like a config file that doesn't exist
            return []
    
    # If path is a directory, use DirectoryCacheProvider
    if cache_path.is_dir():
        return [DirectoryCacheProvider(cache_path, writable=True)]
    
    # If path is a file, load configuration
    if cache_path.is_file():
        return load_cache_config_file(cache_path)
    
    return []


def load_cache_config_file(config_path: Path) -> List:
    """Load cache providers from configuration file.
    
    Args:
        config_path: Path to YAML/JSON configuration file
        
    Returns:
        List of cache provider instances
        
    Configuration file format:
        caches:
          - type: directory
            path: /path/to/cache
            writable: true
          - type: directory
            path: /shared/readonly/cache
            writable: false
    """
    providers = []
    
    with open(config_path, 'r') as f:
        if config_path.suffix in ['.yaml', '.yml']:
            config = yaml.safe_load(f)
        else:
            import json
            config = json.load(f)
    
    if not config or 'caches' not in config:
        return providers
    
    for cache_config in config['caches']:
        cache_type = cache_config.get('type', 'directory')
        
        if cache_type == 'directory':
            cache_dir = Path(cache_config['path'])
            writable = cache_config.get('writable', True)
            
            # Create directory if writable and doesn't exist
            if writable and not cache_dir.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)
            
            providers.append(DirectoryCacheProvider(cache_dir, writable=writable))
        else:
            # Future: support other cache types (remote, etc.)
            pass
    
    return providers
