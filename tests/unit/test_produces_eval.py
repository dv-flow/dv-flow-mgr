#****************************************************************************
#* test_produces_eval.py
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
#****************************************************************************
import pytest
from dv_flow.mgr.produces_eval import ProducesEvaluator


def test_simple_parameter_reference():
    """Test simple parameter reference is resolved."""
    evaluator = ProducesEvaluator()
    patterns = [{"type": "std.FileSet", "filetype": "${{ params.type }}"}]
    
    class Params:
        type = "verilog"
    
    result = evaluator.evaluate(patterns, Params())
    assert len(result) == 1
    assert result[0]["type"] == "std.FileSet"
    assert result[0]["filetype"] == "verilog"


def test_multiple_parameter_references():
    """Test multiple parameter references in one pattern."""
    evaluator = ProducesEvaluator()
    patterns = [{
        "type": "std.FileSet", 
        "filetype": "${{ params.ft }}",
        "vendor": "${{ params.vendor }}"
    }]
    
    class Params:
        ft = "verilog"
        vendor = "synopsys"
    
    result = evaluator.evaluate(patterns, Params())
    assert result[0]["filetype"] == "verilog"
    assert result[0]["vendor"] == "synopsys"


def test_multiple_patterns():
    """Test evaluation of multiple produces patterns."""
    evaluator = ProducesEvaluator()
    patterns = [
        {"type": "std.FileSet", "filetype": "${{ params.type1 }}"},
        {"type": "std.FileSet", "filetype": "${{ params.type2 }}"}
    ]
    
    class Params:
        type1 = "verilog"
        type2 = "vhdl"
    
    result = evaluator.evaluate(patterns, Params())
    assert len(result) == 2
    assert result[0]["filetype"] == "verilog"
    assert result[1]["filetype"] == "vhdl"


def test_no_parameter_references():
    """Test patterns without parameter references pass through unchanged."""
    evaluator = ProducesEvaluator()
    patterns = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    result = evaluator.evaluate(patterns, None)
    assert result[0]["type"] == "std.FileSet"
    assert result[0]["filetype"] == "verilog"


def test_non_string_values_unchanged():
    """Test non-string values are passed through."""
    evaluator = ProducesEvaluator()
    patterns = [{"type": "std.FileSet", "count": 42, "enabled": True}]
    
    result = evaluator.evaluate(patterns, None)
    assert result[0]["count"] == 42
    assert result[0]["enabled"] is True


def test_invalid_reference_handled():
    """Test invalid reference doesn't crash."""
    evaluator = ProducesEvaluator()
    patterns = [{"type": "std.FileSet", "filetype": "${{ params.invalid }}"}]
    
    class Params:
        pass
    
    # Should log warning but not crash, returns original string
    result = evaluator.evaluate(patterns, Params())
    assert len(result) == 1
    # Should have returned the original unevaluated string
    assert "invalid" in result[0]["filetype"] or result[0]["filetype"] == "${{ params.invalid }}"


def test_empty_patterns():
    """Test empty produces patterns list."""
    evaluator = ProducesEvaluator()
    result = evaluator.evaluate([], None)
    assert result == []


def test_none_patterns():
    """Test None produces patterns."""
    evaluator = ProducesEvaluator()
    result = evaluator.evaluate(None, None)
    assert result == []


def test_nested_attribute_access():
    """Test nested parameter attribute access."""
    evaluator = ProducesEvaluator()
    patterns = [{"type": "std.FileSet", "filetype": "${{ params.config.type }}"}]
    
    class Config:
        type = "verilog"
    
    class Params:
        config = Config()
    
    result = evaluator.evaluate(patterns, Params())
    assert result[0]["filetype"] == "verilog"


def test_mixed_static_and_dynamic():
    """Test pattern with both static and dynamic values."""
    evaluator = ProducesEvaluator()
    patterns = [{
        "type": "std.FileSet",
        "filetype": "${{ params.type }}",
        "category": "design",
        "version": "${{ params.version }}"
    }]
    
    class Params:
        type = "verilog"
        version = "2.0"
    
    result = evaluator.evaluate(patterns, Params())
    assert result[0]["type"] == "std.FileSet"
    assert result[0]["filetype"] == "verilog"
    assert result[0]["category"] == "design"
    assert result[0]["version"] == "2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
