"""results.formats config, --results-format, and `show results --format`."""
import json
import os
import sys

import pytest

from dv_flow.mgr.__main__ import get_parser
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.results.config import (ResultsConfig, load_results_config,
                                        parse_formats)


@pytest.fixture(autouse=True)
def reset_extrgy(monkeypatch):
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    monkeypatch.delenv("DFM_RESULTS_FORMATS", raising=False)
    monkeypatch.setenv("HOME", "/nonexistent-home")
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path


def test_parse_formats():
    assert parse_formats(["junit,ctrf", "md", "junit"]) == ["junit", "ctrf", "md"]
    with pytest.raises(ValueError):
        parse_formats(["xml"])


def test_config_defaults(tmp_path):
    cfg = load_results_config(str(tmp_path))
    assert cfg == ResultsConfig()
    assert cfg.keep_previous == 1 and cfg.tree is True and cfg.formats == []


@pytest.mark.parametrize("text,want", [
    ("keep_previous: all", None), ("keep_previous: 0", 0),
    ("keep: 20", 19), ("keep: 0", None)])
def test_config_keep_previous(tmp_path, text, want):
    (tmp_path / ".dfm").mkdir()
    (tmp_path / ".dfm" / "config.yaml").write_text("results:\n  %s\n" % text)
    assert load_results_config(str(tmp_path)).keep_previous == want


def test_config_project_file(tmp_path, monkeypatch, caplog):
    (tmp_path / ".dfm").mkdir()
    (tmp_path / ".dfm" / "config.yaml").write_text(
        "results:\n  keep_previous: 3\n  formats: [junit]\n  copy_logs: true\n  bogus: 1\n")
    cfg = load_results_config(str(tmp_path))
    assert (cfg.keep_previous, cfg.formats, cfg.copy_logs) == (3, ["junit"], True)
    assert any("results.bogus" in r.getMessage() for r in caplog.records)
    monkeypatch.setenv("DFM_RESULTS_FORMATS", "ctrf")
    assert load_results_config(str(tmp_path)).formats == ["ctrf"]


FLOW = """
package:
  name: fm
  tasks:
  - name: hello
    shell: bash
    run: echo hello
"""


def _cli(tmp_path, *argv):
    from dv_flow.mgr.cmds.cmd_run import CmdRun
    (tmp_path / "flow.dv").write_text(FLOW)
    args = get_parser().parse_args(["run", "--root", str(tmp_path)] + list(argv))
    old = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        return CmdRun()(args)
    finally:
        os.chdir(old)


def test_run_writes_configured_formats(tmp_path):
    (tmp_path / ".dfm").mkdir()
    (tmp_path / ".dfm" / "config.yaml").write_text("results:\n  formats: [junit]\n")
    assert _cli(tmp_path, "fm.hello") == 0
    out = tmp_path / "rundir" / "out" / "latest"
    assert (out / "junit.xml").is_file()
    assert not (out / "ctrf.json").exists()
    assert (out / "summary.md").is_file()


def test_run_results_format_flag(tmp_path):
    assert _cli(tmp_path, "--results-format", "junit,ctrf", "fm.hello") == 0
    out = tmp_path / "rundir" / "out" / "latest"
    assert (out / "junit.xml").is_file() and (out / "ctrf.json").is_file()
    d = json.load(open(out / "ctrf.json"))
    assert d["results"]["summary"]["passed"] == 1


def test_run_results_format_bad(tmp_path, capsys):
    assert _cli(tmp_path, "--results-format", "xml", "fm.hello") == 1
    assert "unknown results format" in capsys.readouterr().err


def test_show_results_format(tmp_path, capsys):
    assert _cli(tmp_path, "fm.hello") == 0
    capsys.readouterr()
    rd = str(tmp_path / "rundir")
    for fmt, needle in (("junit", "<testsuites"), ("ctrf", '"reportFormat": "CTRF"'),
                        ("md", "# "), ("json", '"schema": "dvflow-results/1"')):
        args = get_parser().parse_args(["show", "results", "--rundir", rd, "--format", fmt])
        assert args.func(args) == 0
        assert needle in capsys.readouterr().out
    o = tmp_path / "r.xml"
    args = get_parser().parse_args(["show", "results", "--rundir", rd, "--format", "junit",
                                    "-o", str(o)])
    assert args.func(args) == 0
    assert o.read_text().startswith("<?xml")
