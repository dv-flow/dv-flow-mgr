import argparse
from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.util import parse_parameter_overrides

def test_cli_collects_param_overrides_run_subcommand():
    parser = get_parser()
    args = parser.parse_args(["run", "-D", "x=1", "-Dflag=true", "build"])
    assert isinstance(args.param_overrides, list)
    # Accept both spaced and attached forms
    assert "x=1" in args.param_overrides
    assert "flag=true" in args.param_overrides

    ov = parse_parameter_overrides(args.param_overrides)
    assert ov == {"x": "1", "flag": "true"}

def test_cli_collects_param_overrides_graph_and_show():
    parser = get_parser()
    args_g = parser.parse_args(["graph", "-Dfoo=bar"])
    assert args_g.param_overrides == ["foo=bar"]
    ov_g = parse_parameter_overrides(args_g.param_overrides)
    assert ov_g == {"foo": "bar"}

    args_s = parser.parse_args(["show", "packages", "-D", "name=value"])
    assert args_s.param_overrides == ["name=value"]
    ov_s = parse_parameter_overrides(args_s.param_overrides)
    assert ov_s == {"name": "value"}
