#****************************************************************************
#* test_filter_def.py
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
"""Tests for FilterDef model"""
import pytest
from pydantic import ValidationError
from dv_flow.mgr.filter_def import FilterDef
from dv_flow.mgr.param_def import ParamDef


class TestFilterDefBasic:
    """Basic FilterDef creation and validation tests"""
    
    def test_simple_jq_filter(self):
        """Test simple jq expression filter"""
        filter_def = FilterDef(
            name="test_filter",
            expr=".[] | select(.type == 'foo')"
        )
        
        assert filter_def.name == "test_filter"
        assert filter_def.expr == ".[] | select(.type == 'foo')"
        assert filter_def.run is None
        assert filter_def.shell == "bash"  # default
    
    def test_python_filter(self):
        """Test Python implementation filter"""
        filter_def = FilterDef(
            name="python_filter",
            run="def filter(input_data, **kwargs):\n    return len(input_data)",
            shell="python3"
        )
        
        assert filter_def.name == "python_filter"
        assert filter_def.run is not None
        assert filter_def.shell == "python3"
        assert filter_def.expr is None
    
    def test_shell_filter(self):
        """Test shell script filter"""
        filter_def = FilterDef(
            name="shell_filter",
            run="echo 'processing' && cat",
            shell="bash"
        )
        
        assert filter_def.name == "shell_filter"
        assert filter_def.run is not None
        assert filter_def.shell == "bash"
        assert filter_def.expr is None
    
    def test_filter_with_parameters(self):
        """Test filter with parameters using 'with' alias"""
        filter_def = FilterDef(
            name="parameterized",
            **{
                "with": {
                    "threshold": ParamDef(type="float", value=80.0),
                    "mode": ParamDef(type="str", value="strict")
                }
            },
            expr=".[] | select(.score >= $threshold)"
        )
        
        assert filter_def.name == "parameterized"
        assert filter_def.params is not None
        assert "threshold" in filter_def.params
        assert "mode" in filter_def.params
    
    def test_filter_with_documentation(self):
        """Test filter with desc and doc fields"""
        filter_def = FilterDef(
            name="documented",
            desc="Short description",
            doc="Long detailed documentation\nwith multiple lines",
            expr=".[]"
        )
        
        assert filter_def.desc == "Short description"
        assert "multiple lines" in filter_def.doc


class TestFilterDefVisibility:
    """Tests for visibility markers and consolidation"""
    
    def test_inline_name_marker(self):
        """Test filter with inline 'name:' marker"""
        filter_def = FilterDef(
            name="my_filter",
            expr=".[]"
        )
        
        assert filter_def.name == "my_filter"
        assert filter_def.scope is None  # default visibility
    
    def test_inline_export_marker(self):
        """Test filter with inline 'export:' marker"""
        filter_def = FilterDef(
            export="exported_filter",
            expr=".[]"
        )
        
        assert filter_def.name == "exported_filter"
        assert filter_def.scope == "export"
        assert filter_def.export is None  # cleared after consolidation
    
    def test_inline_local_marker(self):
        """Test filter with inline 'local:' marker"""
        filter_def = FilterDef(
            local="local_filter",
            expr=".[]"
        )
        
        assert filter_def.name == "local_filter"
        assert filter_def.scope == "local"
        assert filter_def.local is None
    
    def test_inline_root_marker(self):
        """Test filter with inline 'root:' marker"""
        filter_def = FilterDef(
            root="root_filter",
            expr=".[]"
        )
        
        assert filter_def.name == "root_filter"
        assert filter_def.scope == "root"
        assert filter_def.root is None
    
    def test_explicit_scope(self):
        """Test filter with explicit scope field"""
        filter_def = FilterDef(
            name="scoped_filter",
            scope=["pkg1", "pkg2"],
            expr=".[]"
        )
        
        assert filter_def.name == "scoped_filter"
        assert filter_def.scope == ["pkg1", "pkg2"]
    
    def test_multiple_visibility_markers_error(self):
        """Test that multiple visibility markers raise error"""
        with pytest.raises(ValidationError, match="multiple visibility markers"):
            FilterDef(
                name="conflict1",
                export="conflict2",
                expr=".[]"
            )
    
    def test_scope_without_name_error(self):
        """Test that scope without name raises error"""
        with pytest.raises(ValidationError, match="scope.*requires.*name"):
            FilterDef(
                scope="export",
                expr=".[]"
            )


class TestFilterDefImplementation:
    """Tests for implementation validation"""
    
    def test_missing_implementation_error(self):
        """Test that filter without implementation raises error"""
        with pytest.raises(ValidationError, match="must specify either"):
            FilterDef(name="incomplete")
    
    def test_both_expr_and_run_error(self):
        """Test that both expr and run raises error"""
        with pytest.raises(ValidationError, match="mutually exclusive"):
            FilterDef(
                name="conflict",
                expr=".[]",
                run="echo test"
            )
    
    def test_expr_only_valid(self):
        """Test that expr alone is valid"""
        filter_def = FilterDef(name="expr_only", expr=".[]")
        assert filter_def.expr is not None
        assert filter_def.run is None
    
    def test_run_only_valid(self):
        """Test that run alone is valid"""
        filter_def = FilterDef(name="run_only", run="echo test")
        assert filter_def.run is not None
        assert filter_def.expr is None


class TestFilterDefVisibilityChecks:
    """Tests for is_visible_to() method"""
    
    def test_default_visibility(self):
        """Test default visibility (visible to all)"""
        filter_def = FilterDef(name="default", expr=".[]")
        
        assert filter_def.is_visible_to("pkg1", "root") is True
        assert filter_def.is_visible_to("pkg2", "root") is True
        assert filter_def.is_visible_to("root", "root") is True
    
    def test_export_visibility(self):
        """Test export visibility (visible to all)"""
        filter_def = FilterDef(export="exported", expr=".[]")
        
        assert filter_def.is_visible_to("pkg1", "root") is True
        assert filter_def.is_visible_to("pkg2", "root") is True
        assert filter_def.is_visible_to("root", "root") is True
    
    def test_local_visibility(self):
        """Test local visibility (not visible to others)"""
        filter_def = FilterDef(local="local_only", expr=".[]")
        
        # Local filters are fragment-only, not visible to any package
        assert filter_def.is_visible_to("pkg1", "root") is False
        assert filter_def.is_visible_to("root", "root") is False
    
    def test_root_visibility(self):
        """Test root visibility (only visible to root)"""
        filter_def = FilterDef(root="root_only", expr=".[]")
        
        assert filter_def.is_visible_to("root", "root") is True
        assert filter_def.is_visible_to("pkg1", "root") is False
        assert filter_def.is_visible_to("pkg2", "root") is False
    
    def test_explicit_package_list_visibility(self):
        """Test explicit package list visibility"""
        filter_def = FilterDef(
            name="selective",
            scope=["pkg1", "pkg3"],
            expr=".[]"
        )
        
        assert filter_def.is_visible_to("pkg1", "root") is True
        assert filter_def.is_visible_to("pkg2", "root") is False
        assert filter_def.is_visible_to("pkg3", "root") is True
        assert filter_def.is_visible_to("root", "root") is False


class TestFilterDefEdgeCases:
    """Edge case tests"""
    
    def test_empty_name_error(self):
        """Test that filter without any name marker raises error"""
        with pytest.raises(ValidationError, match="must have a name"):
            FilterDef(expr=".[]")
    
    def test_whitespace_name_valid(self):
        """Test that whitespace in name is allowed (though not recommended)"""
        filter_def = FilterDef(name="  spaced  ", expr=".[]")
        assert filter_def.name == "  spaced  "
    
    def test_special_chars_in_name(self):
        """Test that special characters in name are allowed"""
        filter_def = FilterDef(name="my-filter_v2.0", expr=".[]")
        assert filter_def.name == "my-filter_v2.0"
    
    def test_multiline_expr(self):
        """Test multiline jq expression"""
        expr = """.[] | 
        select(.type == "foo") | 
        .value"""
        filter_def = FilterDef(name="multiline", expr=expr)
        assert filter_def.expr == expr
    
    def test_multiline_run_script(self):
        """Test multiline run script"""
        script = """
def filter(input_data, **kwargs):
    result = []
    for item in input_data:
        if item.get('valid'):
            result.append(item)
    return result
"""
        filter_def = FilterDef(name="multiline_py", run=script, shell="python3")
        assert filter_def.run == script


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
