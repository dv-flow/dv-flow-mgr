#****************************************************************************
#* test_dataflow_matcher.py
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
from dv_flow.mgr.dataflow_matcher import DataflowMatcher
from dv_flow.mgr.task_def import ConsumesE


def test_exact_match():
    """Test exact pattern match is compatible."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet", "filetype": "verilog"}]
    consumes = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible
    assert msg is None


def test_subset_match():
    """Test produce with extra attributes matches."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet", "filetype": "verilog", "vendor": "synopsys"}]
    consumes = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


def test_mismatch_detected():
    """Test mismatch is detected."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet", "filetype": "verilog"}]
    consumes = [{"type": "std.FileSet", "filetype": "vhdl"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert not compatible
    assert "vhdl" in msg
    assert "Producer" in msg
    assert "Consumer" in msg


def test_consumes_all_always_matches():
    """Test ConsumesE.All accepts anything."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, ConsumesE.All, "Producer", "Consumer")
    assert compatible


def test_consumes_none_with_consumes():
    """An UNDECLARED `consumes` is not a claim of compatibility.

    The matcher does not report a mismatch (it has nothing to check against),
    but `dfm validate` reports the gap separately -- the whole point of keeping
    "never said" distinct from "said all" is that silence should not read as a
    positive answer.
    """
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, None, "Producer", "Consumer")
    assert compatible


def test_consumes_no_requires_empty():
    """`consumes: none` and a producing input.

    `consumes: none` means "I do not READ these inputs", not "nothing may flow
    to me". A task that forwards what it does not consume is the ordinary
    aggregator idiom (`std.FileSet` with `passthrough: all` collecting other
    filesets), so the items are not dropped and there is nothing to report --
    `passthrough` is what distinguishes the two cases.
    """
    matcher = DataflowMatcher()
    
    # Empty produces - compatible
    compatible, msg = matcher.check_compatibility(
        [], ConsumesE.No, "Producer", "Consumer")
    assert compatible
    
    # None produces - compatible
    compatible, msg = matcher.check_compatibility(
        None, ConsumesE.No, "Producer", "Consumer")
    assert compatible
    
    # Non-empty produces and the task DOES forward (the default): the items
    # are not dropped, so there is nothing to report. This is the aggregator.
    compatible, msg = matcher.check_compatibility(
        [{"type": "std.FileSet"}], ConsumesE.No, "Producer", "Consumer")
    assert compatible

    # Non-empty produces and the task does NOT forward: the producer's output
    # really is discarded here, which is worth reporting.
    from dv_flow.mgr.task_def import PassthroughE
    compatible, msg = matcher.check_compatibility(
        [{"type": "std.FileSet"}], ConsumesE.No, "Producer", "Consumer",
        passthrough=PassthroughE.No)
    assert not compatible
    assert "discarded" in msg


def test_no_produces_assumed_compatible():
    """Test that missing produces is assumed compatible."""
    matcher = DataflowMatcher()
    consumes = [{"type": "std.FileSet", "filetype": "verilog"}]
    
    # None produces
    compatible, msg = matcher.check_compatibility(
        None, consumes, "Producer", "Consumer")
    assert compatible
    
    # Empty list produces
    compatible, msg = matcher.check_compatibility(
        [], consumes, "Producer", "Consumer")
    assert compatible


def test_multiple_produces_patterns_or_logic():
    """Test multiple produces patterns with OR logic."""
    matcher = DataflowMatcher()
    produces = [
        {"type": "std.FileSet", "filetype": "verilog"},
        {"type": "std.FileSet", "filetype": "vhdl"}
    ]
    consumes = [
        {"type": "std.FileSet", "filetype": "vhdl"}  # Matches second produces
    ]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


def test_multiple_consumes_patterns_or_logic():
    """Test multiple consumes patterns with OR logic."""
    matcher = DataflowMatcher()
    produces = [
        {"type": "std.FileSet", "filetype": "verilog"}
    ]
    consumes = [
        {"type": "std.FileSet", "filetype": "vhdl"},  # Doesn't match
        {"type": "std.FileSet", "filetype": "verilog"}  # Matches!
    ]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible  # Second consume pattern matches


def test_both_multiple_patterns_or_logic():
    """Test OR logic with multiple patterns on both sides."""
    matcher = DataflowMatcher()
    produces = [
        {"type": "std.FileSet", "filetype": "verilog"},
        {"type": "std.FileSet", "filetype": "systemverilog"}
    ]
    consumes = [
        {"type": "std.FileSet", "filetype": "vhdl"},  # No match
        {"type": "std.FileSet", "filetype": "systemverilog"}  # Matches!
    ]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


def test_no_match_all_combinations():
    """Test when no consume pattern matches any produce pattern."""
    matcher = DataflowMatcher()
    produces = [
        {"type": "std.FileSet", "filetype": "verilog"},
        {"type": "std.FileSet", "filetype": "systemverilog"}
    ]
    consumes = [
        {"type": "std.FileSet", "filetype": "vhdl"},
        {"type": "std.FileSet", "filetype": "c"}
    ]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert not compatible
    assert "No consume pattern matches any produce pattern" in msg


def test_missing_attribute_in_produces():
    """Test when consume requires attribute not in produces."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet"}]
    consumes = [{"type": "std.FileSet", "vendor": "synopsys"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert not compatible


def test_complex_matching():
    """Test complex matching with multiple attributes."""
    matcher = DataflowMatcher()
    produces = [
        {
            "type": "std.FileSet",
            "filetype": "verilog",
            "vendor": "synopsys",
            "version": "2023.09"
        }
    ]
    consumes = [
        {
            "type": "std.FileSet",
            "filetype": "verilog",
            "vendor": "synopsys"
        }
    ]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


def test_type_only_matching():
    """Test matching on type alone."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet", "filetype": "verilog"}]
    consumes = [{"type": "std.FileSet"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


def test_different_types_no_match():
    """Test different types don't match."""
    matcher = DataflowMatcher()
    produces = [{"type": "std.FileSet"}]
    consumes = [{"type": "custom.DataSet"}]
    
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert not compatible


def test_empty_patterns():
    """Test with empty pattern dictionaries."""
    matcher = DataflowMatcher()
    produces = [{}]
    consumes = [{}]
    
    # Empty patterns should match (no attributes to check)
    compatible, msg = matcher.check_compatibility(
        produces, consumes, "Producer", "Consumer")
    assert compatible


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
