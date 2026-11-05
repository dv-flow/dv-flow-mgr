"""Rundir store config resolution: layer precedence, provenance, project
opt-out, legacy user config, env/CLI overrides."""
import logging
import os

import pytest
import yaml

from dv_flow.mgr import config_paths
from dv_flow.mgr.runner_config import load_runner_config
from dv_flow.mgr.site_config import StoreContext
from dv_flow.mgr.store_config import expand_root, resolve_store


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point every config layer at tmp files; returns a writer."""
    paths = {
        "install": tmp_path / "install.yaml",
        "site": tmp_path / "site.yaml",
        "user": tmp_path / "user.yaml",
    }
    monkeypatch.setenv("DFM_INSTALL_CONFIG", str(paths["install"]))
    monkeypatch.setenv("DFM_SITE_CONFIG", str(paths["site"]))
    monkeypatch.setenv("DFM_USER_CONFIG", str(paths["user"]))
    proj = tmp_path / "proj"
    (proj / ".dfm").mkdir(parents=True)
    paths["project"] = proj / ".dfm" / "config.yaml"

    class W:
        root = proj
        p = paths

        def write(self, layer, data):
            paths[layer].write_text(yaml.safe_dump(data))

        def ctx(self, **kw):
            return StoreContext(link=str(proj / "rundir"),
                                project_root=str(proj), package="demo",
                                user=kw.get("user", "alice"), uid=1000,
                                host=kw.get("host", "farm-01"))

        def resolve(self, **kw):
            return resolve_store(self.ctx(), str(proj), **kw)
    return W()


def test_default_local(cfg):
    d = cfg.resolve()
    assert d.root is None and d.provenance == "default:local"


@pytest.mark.parametrize("layer", ["install", "site", "user"])
def test_single_layer(cfg, tmp_path, layer):
    cfg.write(layer, {"store": {"root": str(tmp_path / layer)}})
    d = cfg.resolve()
    assert d.root == str(tmp_path / layer)
    assert d.provenance == "%s-config:%s" % (layer, cfg.p[layer])


@pytest.mark.parametrize("hi,lo", [("user", "site"), ("user", "install"),
                                   ("site", "install")])
def test_layer_precedence(cfg, tmp_path, hi, lo):
    cfg.write(hi, {"store": {"root": str(tmp_path / hi)}})
    cfg.write(lo, {"store": {"root": str(tmp_path / lo)}})
    assert cfg.resolve().root == str(tmp_path / hi)


def test_env_beats_files(cfg, tmp_path, monkeypatch):
    cfg.write("user", {"store": {"root": str(tmp_path / "u")}})
    monkeypatch.setenv("DFM_STORE", str(tmp_path / "e"))
    d = cfg.resolve()
    assert d.root == str(tmp_path / "e") and d.provenance == "env:DFM_STORE"


@pytest.mark.parametrize("val", ["", "local"])
def test_env_disables(cfg, tmp_path, monkeypatch, val):
    cfg.write("user", {"store": {"root": str(tmp_path / "u")}})
    monkeypatch.setenv("DFM_STORE", val)
    d = cfg.resolve()
    assert d.root is None and d.provenance == "env:DFM_STORE"


def test_cli_beats_env(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DFM_STORE", str(tmp_path / "e"))
    d = cfg.resolve(cli_store=str(tmp_path / "c"))
    assert d.root == str(tmp_path / "c") and d.provenance == "cli:--store"


def test_no_store_beats_everything(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DFM_STORE", str(tmp_path / "e"))
    cfg.write("user", {"store": {"root": str(tmp_path / "u")}})
    d = cfg.resolve(cli_no_store=True)
    assert d.root is None and d.provenance == "cli:--no-store"


def test_project_optout_beats_user_site(cfg, tmp_path):
    cfg.write("user", {"store": {"root": str(tmp_path / "u")}})
    cfg.write("site", {"store": {"root": str(tmp_path / "s")}})
    cfg.write("project", {"store": {"root": "local"}})
    d = cfg.resolve()
    assert d.root is None and d.provenance.startswith("project-config:")


def test_project_optout_loses_to_env_and_cli(cfg, tmp_path, monkeypatch):
    cfg.write("project", {"store": {"root": "local"}})
    assert cfg.resolve(cli_store=str(tmp_path / "c")).root == str(tmp_path / "c")
    monkeypatch.setenv("DFM_STORE", str(tmp_path / "e"))
    assert cfg.resolve().root == str(tmp_path / "e")


def test_project_abs_root_ignored(cfg, tmp_path, caplog):
    cfg.write("project", {"store": {"root": str(tmp_path / "p"),
                                    "rules": [{"name": "x", "root": "/y"}]}})
    with caplog.at_level(logging.WARNING):
        d = cfg.resolve()
    assert d.root is None and d.provenance == "default:local"
    assert "may only set 'root: local'" in caplog.text
    assert "not allowed in a project file" in caplog.text


def test_relative_root_rejected(cfg, caplog):
    cfg.write("user", {"store": {"root": "rel/dir"}})
    with caplog.at_level(logging.WARNING):
        d = cfg.resolve()
    assert d.root is None and "not an absolute path" in caplog.text


def test_env_var_expansion(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("SCRATCH", str(tmp_path))
    cfg.write("user", {"store": {"root": "${SCRATCH}/${user}/dfm"}})
    assert cfg.resolve().root == str(tmp_path / "alice" / "dfm")


def test_unresolved_var_skips_layer(cfg, tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("NOPE_NOT_SET", raising=False)
    cfg.write("user", {"store": {"root": "/x/${NOPE_NOT_SET}"}})
    cfg.write("site", {"store": {"root": str(tmp_path / "s")}})
    assert cfg.resolve().root == str(tmp_path / "s")


def test_create_flag(cfg, tmp_path):
    cfg.write("user", {"store": {"root": str(tmp_path / "u"), "create": False}})
    assert cfg.resolve().create is False


def test_full_chain_records_all_layers(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DFM_STORE", str(tmp_path / "e"))
    cfg.write("user", {"store": {"root": str(tmp_path / "u")}})
    cfg.write("site", {"store": {"root": str(tmp_path / "s")}})
    d = cfg.resolve(full=True)
    srcs = [s for s, _ in d.chain]
    assert srcs[0] == "env:DFM_STORE"
    assert any(s.startswith("user-config:") for s in srcs)
    assert any(s.startswith("site-config:") for s in srcs)
    assert d.root == str(tmp_path / "e")


def test_expand_root_home():
    assert expand_root("~/x", None) == os.path.expanduser("~/x")


# ---------------------------------------------------------------- user config paths

def test_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.delenv("DFM_USER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_paths.user_config_paths()[0] == str(tmp_path / "dfm" / "config.yaml")


def test_legacy_site_yaml_alias(tmp_path, monkeypatch):
    monkeypatch.delenv("DFM_USER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "dfm").mkdir()
    (tmp_path / "dfm" / "site.yaml").write_text(
        "store: {root: /legacy}\nrunner: {type: lsf}\n")
    data, used = config_paths.load_user_config()
    assert data["store"]["root"] == "/legacy"
    (tmp_path / "dfm" / "config.yaml").write_text("store: {root: /new}\n")
    data, used = config_paths.load_user_config()
    assert data["store"]["root"] == "/new"       # config.yaml wins
    assert data["runner"]["type"] == "lsf"       # site.yaml still read
    assert used[0].endswith("config.yaml")


def test_runner_config_site_and_user_layers(tmp_path, monkeypatch):
    site = tmp_path / "site.yaml"
    user = tmp_path / "user.yaml"
    site.write_text("runner: {type: lsf, lsf: {queue: siteq}}\n")
    monkeypatch.setenv("DFM_SITE_CONFIG", str(site))
    monkeypatch.setenv("DFM_USER_CONFIG", str(user))
    monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
    monkeypatch.delenv("DFM_RUNNER", raising=False)
    cfg = load_runner_config(project_root=str(tmp_path))
    assert cfg.type == "lsf" and cfg.lsf.queue == "siteq"
    user.write_text("runner: {lsf: {queue: userq}}\n")
    cfg = load_runner_config(project_root=str(tmp_path))
    assert cfg.lsf.queue == "userq"


# ---------------------------------------------------------------- parser

def test_store_flags_on_run_parser():
    import argparse
    from dv_flow.mgr.__main__ import get_parser, reserved_option_strings, _add_run_opts
    p = get_parser()
    a = p.parse_args(["run", "--store", "/s", "--store-recreate", "t"])
    assert a.store == "/s" and a.store_recreate
    a = p.parse_args(["run", "--no-store", "t"])
    assert a.no_store
    with pytest.raises(SystemExit):
        p.parse_args(["run", "--store", "/s", "--no-store", "t"])
    rp = argparse.ArgumentParser()
    _add_run_opts(rp)
    reserved = reserved_option_strings(rp)
    assert "--store" in reserved and "--no-store" in reserved
