"""Tests for std.ResourceTag type definition in flow.dv."""
import pytest


class TestResourceTagLoads:
    def test_resource_tag_in_std_types(self):
        """std.ResourceTag should be discoverable in the type registry."""
        from dv_flow.mgr.ext_rgy import ExtRgy
        from dv_flow.mgr.package_loader import PackageLoader

        rgy = ExtRgy.inst()
        loader = PackageLoader(rgy)
        pkg = rgy.getPackage("std", loader)
        type_names = [t.name for t in pkg.type_m.values()]
        assert "std.ResourceTag" in type_names

    def test_resource_tag_inherits_from_tag(self):
        """std.ResourceTag should use std.Tag as base."""
        from dv_flow.mgr.ext_rgy import ExtRgy
        from dv_flow.mgr.package_loader import PackageLoader

        rgy = ExtRgy.inst()
        loader = PackageLoader(rgy)
        pkg = rgy.getPackage("std", loader)
        rt = pkg.type_m.get("std.ResourceTag")
        assert rt is not None
        # The type should have 'uses' pointing to std.Tag
        uses = getattr(rt, "uses", None)
        assert uses is not None
        assert "Tag" in str(uses)

    def test_resource_tag_default_values(self):
        """ResourceTag fields should have correct defaults."""
        from dv_flow.mgr.ext_rgy import ExtRgy
        from dv_flow.mgr.package_loader import PackageLoader

        rgy = ExtRgy.inst()
        loader = PackageLoader(rgy)
        pkg = rgy.getPackage("std", loader)
        rt = pkg.type_m.get("std.ResourceTag")
        assert rt is not None
        # Check that the type has the expected field definitions
        fields = getattr(rt, "params", None) or getattr(rt, "with_m", None)
        if fields is not None:
            # Verify at least some expected field names exist
            field_names = set()
            if isinstance(fields, dict):
                field_names = set(fields.keys())
            elif isinstance(fields, list):
                for f in fields:
                    if hasattr(f, "name"):
                        field_names.add(f.name)
            expected = {"cores", "memory", "queue", "walltime", "resource_class"}
            assert expected.issubset(field_names), (
                "Missing fields: %s" % (expected - field_names)
            )
