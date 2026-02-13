#****************************************************************************
#* test_filter_registry.py
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
"""Tests for FilterRegistry"""
import pytest
from dv_flow.mgr.filter_registry import FilterRegistry
from dv_flow.mgr.filter_def import FilterDef


class TestFilterRegistryBasic:
    """Basic filter registration and lookup tests"""
    
    def test_register_and_resolve_simple(self):
        """Test simple filter registration and resolution"""
        registry = FilterRegistry()
        
        filter1 = FilterDef(name="filter1", expr=".[]")
        registry.register_package_filters("pkg1", [filter1], [])
        
        # Resolve from same package
        resolved = registry.resolve_filter("pkg1", "filter1")
        assert resolved is not None
        assert resolved.name == "filter1"
    
    def test_filter_not_found(self):
        """Test that non-existent filter returns None"""
        registry = FilterRegistry()
        
        resolved = registry.resolve_filter("pkg1", "nonexistent")
        assert resolved is None
    
    def test_multiple_filters_in_package(self):
        """Test registering multiple filters"""
        registry = FilterRegistry()
        
        filters = [
            FilterDef(name="filter1", expr=".[]"),
            FilterDef(name="filter2", expr=".field"),
            FilterDef(name="filter3", expr=".value")
        ]
        registry.register_package_filters("pkg1", filters, [])
        
        # All should be resolvable
        assert registry.resolve_filter("pkg1", "filter1") is not None
        assert registry.resolve_filter("pkg1", "filter2") is not None
        assert registry.resolve_filter("pkg1", "filter3") is not None
    
    def test_multiple_packages(self):
        """Test filters in multiple packages"""
        registry = FilterRegistry()
        
        registry.register_package_filters(
            "pkg1",
            [FilterDef(name="filter1", expr=".[]")],
            []
        )
        registry.register_package_filters(
            "pkg2",
            [FilterDef(name="filter2", expr=".field")],
            []
        )
        
        # Each package can access its own filters
        assert registry.resolve_filter("pkg1", "filter1") is not None
        assert registry.resolve_filter("pkg2", "filter2") is not None
        
        # But not other packages' filters (without imports)
        assert registry.resolve_filter("pkg1", "filter2") is None
        assert registry.resolve_filter("pkg2", "filter1") is None


class TestFilterRegistryImports:
    """Tests for filter resolution with imports"""
    
    def test_import_makes_filter_visible(self):
        """Test that importing a package makes its exported filters visible"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A defines an exported filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(export="shared_filter", expr=".[]")],
            []
        )
        
        # Package B imports A
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # B can access A's exported filter
        resolved = registry.resolve_filter("pkgB", "shared_filter")
        assert resolved is not None
        assert resolved.name == "shared_filter"
    
    def test_local_filter_not_visible_to_imports(self):
        """Test that local filters are not visible to importing packages"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has a local filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(local="private_filter", expr=".[]")],
            []
        )
        
        # Package B imports A
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # B cannot access A's local filter
        resolved = registry.resolve_filter("pkgB", "private_filter")
        assert resolved is None
    
    def test_local_shadowing(self):
        """Test that local filters shadow imported ones"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has a filter
        filterA = FilterDef(export="common_filter", expr=".[] | select(.a)")
        registry.register_package_filters("pkgA", [filterA], [])
        
        # Package B imports A and redefines the filter
        filterB = FilterDef(name="common_filter", expr=".[] | select(.b)")
        registry.register_package_filters("pkgB", [filterB], ["pkgA"])
        
        # B should get its local version
        resolved = registry.resolve_filter("pkgB", "common_filter")
        assert resolved is not None
        assert resolved.expr == ".[] | select(.b)"  # B's version


class TestFilterRegistryQualifiedNames:
    """Tests for qualified filter names (pkg.filter)"""
    
    def test_qualified_name_resolution(self):
        """Test resolving qualified filter names"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Register filter in pkgA
        registry.register_package_filters(
            "pkgA",
            [FilterDef(export="filter1", expr=".[]")],
            []
        )
        
        # Register pkgB with import
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # B can access via qualified name
        resolved = registry.resolve_filter("pkgB", "pkgA.filter1")
        assert resolved is not None
        assert resolved.name == "filter1"
    
    def test_qualified_name_bypasses_shadowing(self):
        """Test that qualified names bypass local shadowing"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has a filter
        filterA = FilterDef(export="shared", expr=".a")
        registry.register_package_filters("pkgA", [filterA], [])
        
        # Package B shadows it
        filterB = FilterDef(name="shared", expr=".b")
        registry.register_package_filters("pkgB", [filterB], ["pkgA"])
        
        # Unqualified name gets B's version
        resolved = registry.resolve_filter("pkgB", "shared")
        assert resolved.expr == ".b"
        
        # Qualified name gets A's version
        resolved = registry.resolve_filter("pkgB", "pkgA.shared")
        assert resolved.expr == ".a"
    
    def test_qualified_name_respects_visibility(self):
        """Test that qualified names still respect visibility"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has a local filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(local="private", expr=".[]")],
            []
        )
        
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # B cannot access via qualified name (local visibility)
        resolved = registry.resolve_filter("pkgB", "pkgA.private")
        assert resolved is None


class TestFilterRegistryVisibility:
    """Tests for visibility rules"""
    
    def test_root_visibility(self):
        """Test root visibility (only root package can access)"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has a root-scoped filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(root="root_only", expr=".[]")],
            []
        )
        
        # Root package imports A
        registry.register_package_filters("root", [], ["pkgA"])
        
        # Another package imports A
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # Root can access
        assert registry.resolve_filter("root", "root_only") is not None
        
        # Other packages cannot
        assert registry.resolve_filter("pkgB", "root_only") is None
    
    def test_export_visibility(self):
        """Test export visibility (visible to all downstream)"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A exports a filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(export="public_filter", expr=".[]")],
            []
        )
        
        # Multiple packages import A
        registry.register_package_filters("pkgB", [], ["pkgA"])
        registry.register_package_filters("pkgC", [], ["pkgA"])
        
        # All can access
        assert registry.resolve_filter("pkgB", "public_filter") is not None
        assert registry.resolve_filter("pkgC", "public_filter") is not None
    
    def test_default_visibility(self):
        """Test default visibility (visible to all)"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has default visibility filter
        registry.register_package_filters(
            "pkgA",
            [FilterDef(name="default_filter", expr=".[]")],
            []
        )
        
        registry.register_package_filters("pkgB", [], ["pkgA"])
        
        # B can access (default is visible)
        assert registry.resolve_filter("pkgB", "default_filter") is not None


class TestFilterRegistryUtilities:
    """Tests for utility methods"""
    
    def test_get_package_filters(self):
        """Test getting all filters from a package"""
        registry = FilterRegistry()
        
        filters = [
            FilterDef(name="filter1", expr=".[]"),
            FilterDef(name="filter2", expr=".field")
        ]
        registry.register_package_filters("pkg1", filters, [])
        
        pkg_filters = registry.get_package_filters("pkg1")
        assert len(pkg_filters) == 2
        assert "filter1" in pkg_filters
        assert "filter2" in pkg_filters
    
    def test_get_visible_filters(self):
        """Test getting all visible filters for a package"""
        registry = FilterRegistry()
        registry.set_root_package("root")
        
        # Package A has filters
        registry.register_package_filters(
            "pkgA",
            [
                FilterDef(export="public1", expr=".[]"),
                FilterDef(local="private1", expr=".[]")
            ],
            []
        )
        
        # Package B imports A and has its own
        registry.register_package_filters(
            "pkgB",
            [FilterDef(name="local1", expr=".[]")],
            ["pkgA"]
        )
        
        visible = registry.get_visible_filters("pkgB")
        
        # Should have public1 from A and local1 from B
        assert "public1" in visible
        assert "local1" in visible
        # Should not have private1 (local to A)
        assert "private1" not in visible
    
    def test_list_all_filters(self):
        """Test listing all filters"""
        registry = FilterRegistry()
        
        registry.register_package_filters(
            "pkg1",
            [FilterDef(name="f1", expr=".[]")],
            []
        )
        registry.register_package_filters(
            "pkg2",
            [FilterDef(name="f2", expr=".[]"), FilterDef(name="f3", expr=".[]")],
            []
        )
        
        all_filters = registry.list_all_filters()
        
        assert "pkg1" in all_filters
        assert "pkg2" in all_filters
        assert all_filters["pkg1"] == ["f1"]
        assert set(all_filters["pkg2"]) == {"f2", "f3"}
    
    def test_clear(self):
        """Test clearing registry"""
        registry = FilterRegistry()
        
        registry.register_package_filters(
            "pkg1",
            [FilterDef(name="filter1", expr=".[]")],
            []
        )
        
        assert registry.resolve_filter("pkg1", "filter1") is not None
        
        registry.clear()
        
        assert registry.resolve_filter("pkg1", "filter1") is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
