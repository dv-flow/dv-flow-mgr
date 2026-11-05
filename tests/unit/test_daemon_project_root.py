"""The daemon's .dfm/ state lives at the package root, matching `dfm run`."""
import os

from dv_flow.mgr.cmds.cmd_daemon import CmdDaemon


class _Args:
    def __init__(self, root=None):
        self.root = root


def test_daemon_root_is_package_root_from_subdir(tmp_path, monkeypatch):
    (tmp_path / "flow.yaml").write_text("package:\n  name: p\n")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    monkeypatch.delenv("DV_FLOW_ROOT", raising=False)
    assert CmdDaemon()._get_project_root(_Args()) == str(tmp_path)
    assert CmdDaemon()._get_project_root(_Args(str(tmp_path / "sub"))) == str(tmp_path)


def test_daemon_root_without_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DV_FLOW_ROOT", raising=False)
    assert CmdDaemon()._get_project_root(_Args()) == str(tmp_path)
