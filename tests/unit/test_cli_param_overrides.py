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
    # New format: returns dict with 'package', 'task', and 'leaf' keys
    assert ov['package'] == {"x": "1", "flag": "true"}
    assert ov['task'] == {}
    assert ov['leaf'] == {"x": "1", "flag": "true"}  # Leaf names are also stored

def test_multisegment_pkg_var_override_classified_as_package():
    """A `-D <dotted.pkg>.<var>` (2+ dots) must be offered as a PACKAGE-var
    override candidate, not only a task override -- otherwise a package var of a
    multi-segment package (e.g. `hdlsim.vlt.trace_fmt`) can never be set from the
    CLI. The whole dotted name is kept in 'package'; the package-override
    consumer matches it against real package names (rsplit) and binds only if
    such a package+var exists."""
    ov = parse_parameter_overrides(["hdlsim.vlt.trace_fmt=vcd"])
    # Package candidate: whole name preserved for package-name matching.
    assert ov['package'] == {"hdlsim.vlt.trace_fmt": "vcd"}
    # Task candidate still offered (rest-as-task, last-as-param).
    assert ov['task'] == {"hdlsim.vlt": {"trace_fmt": "vcd"}}


def test_cli_collects_param_overrides_graph_and_show():
    parser = get_parser()
    args_g = parser.parse_args(["graph", "-Dfoo=bar"])
    assert args_g.param_overrides == ["foo=bar"]
    ov_g = parse_parameter_overrides(args_g.param_overrides)
    assert ov_g['package'] == {"foo": "bar"}
    assert ov_g['leaf'] == {"foo": "bar"}

    args_s = parser.parse_args(["show", "packages", "-D", "name=value"])
    assert args_s.param_overrides == ["name=value"]
    ov_s = parse_parameter_overrides(args_s.param_overrides)
    assert ov_s['package'] == {"name": "value"}
    assert ov_s['leaf'] == {"name": "value"}
