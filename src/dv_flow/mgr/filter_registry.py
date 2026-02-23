#****************************************************************************
#* filter_registry.py
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
FilterRegistry - Manages filter definitions and visibility across packages.

The registry:
- Stores filters from all packages
- Resolves filter references (with qualified name support)
- Enforces visibility rules (local, export, root)
- Handles shadowing (local filters override imported ones)
"""
import logging
from typing import Dict, List, Optional, Set
from .filter_def import FilterDef


class FilterRegistry:
    """
    Manages filter definitions and visibility.
    
    Filters are registered by package and resolved with visibility checking.
    Supports qualified names (pkg.filter) and local shadowing.
    """
    
    def __init__(self):
        self._log = logging.getLogger("FilterRegistry")
        
        # Package name -> filter name -> FilterDef
        self._filters: Dict[str, Dict[str, FilterDef]] = {}
        
        # Package name -> list of imported package names
        self._imports: Dict[str, List[str]] = {}
        
        # Track root package for visibility checks
        self._root_package: Optional[str] = None
    
    def set_root_package(self, root_package: str):
        """Set the root package name for visibility checks"""
        self._root_package = root_package
    
    def register_package_filters(self, pkg_name: str, filters: List[FilterDef], imports: List[str]):
        """
        Register filters from a package.
        
        Args:
            pkg_name: Name of the package
            filters: List of FilterDef from the package
            imports: List of imported package names
        """
        if pkg_name not in self._filters:
            self._filters[pkg_name] = {}
        
        # Register each filter
        for filter_def in filters:
            filter_name = filter_def.name
            
            if filter_name in self._filters[pkg_name]:
                self._log.warning(
                    f"Package '{pkg_name}' redefines filter '{filter_name}' "
                    f"(previous definition will be shadowed)"
                )
            
            self._filters[pkg_name][filter_name] = filter_def
            self._log.debug(f"Registered filter: {pkg_name}.{filter_name}")
        
        # Store imports for resolution
        self._imports[pkg_name] = imports
    
    def resolve_filter(self, requesting_pkg: str, filter_name: str) -> Optional[FilterDef]:
        """
        Resolve a filter by name with visibility checking.
        
        Resolution order:
        1. Check for qualified name (pkg.filter) - direct lookup
        2. Check current package
        3. Check imported packages (respecting visibility)
        
        Args:
            requesting_pkg: Name of the package requesting the filter
            filter_name: Name or qualified name (pkg.filter) of the filter
            
        Returns:
            FilterDef if found and visible, None otherwise
        """
        # Handle qualified names (pkg.filter)
        if "." in filter_name:
            return self._resolve_qualified(requesting_pkg, filter_name)
        
        # Check current package first (local shadowing)
        filter_def = self._get_filter(requesting_pkg, filter_name)
        if filter_def is not None:
            # Filters in own package are always visible
            self._log.debug(f"Resolved filter '{filter_name}' in package '{requesting_pkg}'")
            return filter_def
        
        # Search imported packages
        imports = self._imports.get(requesting_pkg, [])
        for imported_pkg in imports:
            filter_def = self._get_filter(imported_pkg, filter_name)
            if filter_def is not None:
                # Check visibility
                if self._is_visible(filter_def, imported_pkg, requesting_pkg):
                    self._log.debug(
                        f"Resolved filter '{filter_name}' from imported package '{imported_pkg}'"
                    )
                    return filter_def
        
        # Not found
        self._log.debug(f"Filter '{filter_name}' not found for package '{requesting_pkg}'")
        return None
    
    def _resolve_qualified(self, requesting_pkg: str, qualified_name: str) -> Optional[FilterDef]:
        """
        Resolve a qualified filter name (pkg.filter).
        
        Args:
            requesting_pkg: Package requesting the filter
            qualified_name: Qualified name in format "pkg.filter"
            
        Returns:
            FilterDef if found and visible, None otherwise
        """
        parts = qualified_name.rsplit(".", 1)
        if len(parts) != 2:
            self._log.warning(f"Invalid qualified filter name: {qualified_name}")
            return None
        
        target_pkg, filter_name = parts
        
        # Get the filter
        filter_def = self._get_filter(target_pkg, filter_name)
        if filter_def is None:
            return None
        
        # Check visibility
        if requesting_pkg == target_pkg:
            # Same package, always visible
            return filter_def
        
        if self._is_visible(filter_def, target_pkg, requesting_pkg):
            self._log.debug(
                f"Resolved qualified filter '{qualified_name}' for package '{requesting_pkg}'"
            )
            return filter_def
        
        self._log.debug(
            f"Filter '{qualified_name}' exists but not visible to package '{requesting_pkg}'"
        )
        return None
    
    def _get_filter(self, pkg_name: str, filter_name: str) -> Optional[FilterDef]:
        """Get a filter from a specific package (no visibility check)"""
        pkg_filters = self._filters.get(pkg_name, {})
        return pkg_filters.get(filter_name)
    
    def _is_visible(self, filter_def: FilterDef, source_pkg: str, target_pkg: str) -> bool:
        """
        Check if a filter is visible to a target package.
        
        Args:
            filter_def: The filter to check
            source_pkg: Package that defines the filter
            target_pkg: Package requesting access
            
        Returns:
            True if filter is visible to target package
        """
        # Use FilterDef's built-in visibility check
        root_pkg = self._root_package or source_pkg
        return filter_def.is_visible_to(target_pkg, root_pkg)
    
    def get_package_filters(self, pkg_name: str) -> Dict[str, FilterDef]:
        """
        Get all filters defined by a specific package.
        
        Args:
            pkg_name: Package name
            
        Returns:
            Dict mapping filter names to FilterDef instances
        """
        return self._filters.get(pkg_name, {}).copy()
    
    def get_visible_filters(self, requesting_pkg: str) -> Dict[str, FilterDef]:
        """
        Get all filters visible to a package.
        
        Returns a dict of filter_name -> FilterDef for all filters
        visible to the requesting package. Local filters shadow imported ones.
        
        Args:
            requesting_pkg: Package name
            
        Returns:
            Dict of visible filters (name -> FilterDef)
        """
        visible = {}
        
        # First, add filters from imported packages
        imports = self._imports.get(requesting_pkg, [])
        for imported_pkg in imports:
            pkg_filters = self._filters.get(imported_pkg, {})
            for filter_name, filter_def in pkg_filters.items():
                if self._is_visible(filter_def, imported_pkg, requesting_pkg):
                    # Only add if not already present (shadowing)
                    if filter_name not in visible:
                        visible[filter_name] = filter_def
        
        # Then, add filters from current package (overrides imports)
        pkg_filters = self._filters.get(requesting_pkg, {})
        for filter_name, filter_def in pkg_filters.items():
            visible[filter_name] = filter_def
        
        return visible
    
    def list_all_filters(self) -> Dict[str, List[str]]:
        """
        List all registered filters by package.
        
        Returns:
            Dict mapping package names to lists of filter names
        """
        return {
            pkg_name: list(filters.keys())
            for pkg_name, filters in self._filters.items()
        }
    
    def clear(self):
        """Clear all registered filters (for testing)"""
        self._filters.clear()
        self._imports.clear()
        self._root_package = None
