"""Tests for parameter file (-P) support"""
import os
import json
import pytest
from dv_flow.mgr.util import load_param_file, merge_parameter_overrides, parse_parameter_overrides


def test_load_simple_json_file(tmpdir):
    """Test loading basic JSON parameter file"""
    param_file = os.path.join(tmpdir, "params.json")
    params = {
        "package": {"timeout": 300},
        "tasks": {
            "build": {"include": ["*.sv", "*.v"]},
            "test": {"debug": True}
        }
    }
    
    with open(param_file, 'w') as f:
        json.dump(params, f)
    
    result = load_param_file(param_file)
    assert result['package'] == {"timeout": 300}
    assert result['task']['build'] == {"include": ["*.sv", "*.v"]}
    assert result['task']['test'] == {"debug": True}


def test_load_complex_types(tmpdir):
    """Test loading complex types from JSON"""
    param_file = os.path.join(tmpdir, "params.json")
    params = {
        "package": {},
        "tasks": {
            "build": {
                "defines": {"DEBUG": 1, "VERBOSE": True},
                "options": {"opt_level": 2, "warnings": ["all", "error"]}
            }
        }
    }
    
    with open(param_file, 'w') as f:
        json.dump(params, f)
    
    result = load_param_file(param_file)
    assert result['task']['build']['defines'] == {"DEBUG": 1, "VERBOSE": True}
    assert result['task']['build']['options'] == {"opt_level": 2, "warnings": ["all", "error"]}


def test_file_not_found_error(tmpdir):
    """Test error handling for missing file"""
    with pytest.raises(Exception, match="Parameter file not found"):
        load_param_file(os.path.join(tmpdir, "nonexistent.json"))


def test_invalid_json_error(tmpdir):
    """Test error handling for invalid JSON"""
    param_file = os.path.join(tmpdir, "params.json")
    with open(param_file, 'w') as f:
        f.write("{invalid json")
    
    with pytest.raises(Exception, match="Error parsing parameter file"):
        load_param_file(param_file)


def test_cli_override_precedence(tmpdir):
    """Test that -D options override -P file values"""
    # File overrides
    file_ov = {
        'package': {'x': 'file_value'},
        'task': {'build': {'include': ['file.txt']}}
    }
    
    # CLI overrides
    cli_ov = parse_parameter_overrides(['x=cli_value', 'build.include=cli.txt'])
    
    # Merge (CLI should win)
    merged = merge_parameter_overrides(cli_ov, file_ov)
    
    assert merged['package']['x'] == 'cli_value'
    assert merged['task']['build']['include'] == 'cli.txt'


def test_merge_multiple_sources(tmpdir):
    """Test merging file and CLI overrides"""
    file_ov = {
        'package': {'x': 'file_x', 'y': 'file_y'},
        'task': {
            'build': {'param1': 'file_p1'},
            'test': {'param2': 'file_p2'}
        }
    }
    
    cli_ov = parse_parameter_overrides(['x=cli_x', 'build.param1=cli_p1'])
    
    merged = merge_parameter_overrides(cli_ov, file_ov)
    
    # CLI overrides 'x' and 'build.param1'
    assert merged['package']['x'] == 'cli_x'
    assert merged['package']['y'] == 'file_y'  # From file
    assert merged['task']['build']['param1'] == 'cli_p1'
    assert merged['task']['test']['param2'] == 'file_p2'  # From file


def test_empty_file(tmpdir):
    """Test handling of empty/minimal JSON file"""
    param_file = os.path.join(tmpdir, "params.json")
    with open(param_file, 'w') as f:
        json.dump({}, f)
    
    result = load_param_file(param_file)
    assert result['package'] == {}
    assert result['task'] == {}


def test_inline_json_string_simple(tmpdir):
    """Test inline JSON string instead of file path"""
    json_string = '{"tasks": {"build": {"top": "counter"}}}'
    
    result = load_param_file(json_string)
    assert result['task']['build'] == {"top": "counter"}
    assert result['package'] == {}


def test_inline_json_string_complex(tmpdir):
    """Test inline JSON with complex nested structure"""
    json_string = '''
    {
        "package": {"timeout": 300},
        "tasks": {
            "build": {
                "defines": {"DEBUG": 1, "VERBOSE": true},
                "options": {"warnings": ["all", "error"]}
            }
        }
    }
    '''
    
    result = load_param_file(json_string)
    assert result['package'] == {"timeout": 300}
    assert result['task']['build']['defines'] == {"DEBUG": 1, "VERBOSE": True}
    assert result['task']['build']['options'] == {"warnings": ["all", "error"]}


def test_inline_json_string_with_whitespace(tmpdir):
    """Test inline JSON with leading/trailing whitespace"""
    json_string = '  {"tasks": {"test": {"param": "value"}}}  '
    
    result = load_param_file(json_string)
    assert result['task']['test'] == {"param": "value"}


def test_inline_json_invalid_string(tmpdir):
    """Test error handling for invalid inline JSON"""
    json_string = '{"invalid json'
    
    with pytest.raises(Exception, match="Error parsing inline JSON"):
        load_param_file(json_string)


def test_file_vs_inline_json_disambiguation(tmpdir):
    """Test that files are loaded as files, not treated as JSON strings"""
    # Create a real file
    param_file = os.path.join(tmpdir, "params.json")
    with open(param_file, 'w') as f:
        json.dump({"tasks": {"build": {"from_file": True}}}, f)
    
    # Load from file path
    result = load_param_file(param_file)
    assert result['task']['build'] == {"from_file": True}
    
    # Now try inline JSON with same structure
    json_string = '{"tasks": {"build": {"from_inline": true}}}'
    result2 = load_param_file(json_string)
    assert result2['task']['build'] == {"from_inline": True}
