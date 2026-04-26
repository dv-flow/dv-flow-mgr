"""Tests for --runner and --runner-opt CLI argument parsing."""
import pytest
from dv_flow.mgr.__main__ import get_parser


class TestRunnerCLI:
    def test_runner_local_accepted(self):
        parser = get_parser()
        args = parser.parse_args(["run", "--runner", "local", "sometask"])
        assert args.runner == "local"

    def test_runner_lsf_accepted(self):
        parser = get_parser()
        args = parser.parse_args(["run", "--runner", "lsf", "sometask"])
        assert args.runner == "lsf"

    def test_runner_default_is_none(self):
        """No --runner flag means runner is None (resolved from config)."""
        parser = get_parser()
        args = parser.parse_args(["run", "sometask"])
        assert args.runner is None

    def test_runner_opt_parsed(self):
        parser = get_parser()
        args = parser.parse_args([
            "run", "--runner-opt", "queue=regr_high",
            "--runner-opt", "project=test", "sometask"
        ])
        assert args.runner_opts == ["queue=regr_high", "project=test"]

    def test_runner_opt_default_empty(self):
        parser = get_parser()
        args = parser.parse_args(["run", "sometask"])
        assert args.runner_opts == []

    def test_runner_with_opts(self):
        parser = get_parser()
        args = parser.parse_args([
            "run", "--runner", "lsf",
            "--runner-opt", "queue=regr_high", "sometask"
        ])
        assert args.runner == "lsf"
        assert args.runner_opts == ["queue=regr_high"]
