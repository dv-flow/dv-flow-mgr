#****************************************************************************
#* cmd_init.py
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
from datetime import datetime
from pathlib import Path


class CmdCacheInit:
    """Initialize a cache directory for DV Flow Manager"""
    
    def __call__(self, args):
        cache_dir = Path(args.cache_dir)
        
        # Create directory structure
        print(f"Initializing cache directory: {cache_dir}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set appropriate permissions for shared cache
        if args.shared:
            print("Setting up shared cache with group write permissions")
            try:
                # Set setgid bit for shared access
                cache_dir.chmod(0o2775)
            except Exception as e:
                print(f"Warning: Could not set permissions: {e}")
        
        # Create .cache_config.yaml
        config = {
            'type': 'directory',
            'version': 1,
            'created': datetime.now().isoformat(),
            'shared': args.shared
        }
        
        config_file = cache_dir / '.cache_config.yaml'
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        print(f"Cache initialized successfully at {cache_dir}")
        print(f"\nTo use this cache, set the environment variable:")
        print(f"  export DV_FLOW_CACHE={cache_dir}")
        
        if args.shared:
            print(f"\nFor shared cache, ensure all users are in the same group")
            print(f"and have write access to this directory.")
        
        return 0
