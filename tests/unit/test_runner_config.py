"""Tests for RunnerConfig loading and merge logic."""
import os
import pytest
import yaml
from dv_flow.mgr.runner_config import (
    RunnerConfig, LsfConfig, PoolConfig, ResourceDefaults, ResourceClassDef,
    load_runner_config, _merge_layer, _merge_lsf, _load_yaml,
)


class TestRunnerConfigDefaults:
    def test_empty_config(self):
        cfg = RunnerConfig()
        assert cfg.type == "local"
        assert cfg.pool.min_workers == 0
        assert cfg.pool.max_workers == 16
        assert cfg.lsf.bsub_cmd == "bsub"
        assert cfg.defaults.memory == "1G"
        assert cfg.resource_classes == {}

    def test_lsf_config_defaults(self):
        lsf = LsfConfig()
        assert lsf.bsub_cmd == "bsub"
        assert lsf.queue == ""
        assert lsf.project == ""
        assert lsf.resource_select == []
        assert lsf.bsub_extra == []
        assert lsf.worker_dfm_path == "dfm"


class TestLoadYaml:
    def test_missing_file_returns_empty(self):
        assert _load_yaml("/nonexistent/file.yaml") == {}

    def test_none_path_returns_empty(self):
        assert _load_yaml(None) == {}

    def test_empty_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        assert _load_yaml(str(p)) == {}

    def test_valid_yaml(self, tmp_path):
        p = tmp_path / "test.yaml"
        p.write_text("runner:\n  default: lsf\n")
        data = _load_yaml(str(p))
        assert data["runner"]["default"] == "lsf"

    def test_malformed_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("[not a mapping")
        with pytest.raises(Exception):
            _load_yaml(str(p))

    def test_non_mapping_raises(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            _load_yaml(str(p))


class TestMergeLsf:
    def test_empty_overlay(self):
        base = LsfConfig()
        result = _merge_lsf(base, {})
        assert result.bsub_cmd == "bsub"

    def test_scalar_last_writer_wins(self):
        base = LsfConfig(bsub_cmd="bsub", queue="normal")
        result = _merge_lsf(base, {"queue": "regr_high", "bsub_cmd": "lsf_bsub"})
        assert result.queue == "regr_high"
        assert result.bsub_cmd == "lsf_bsub"

    def test_list_accumulated(self):
        base = LsfConfig(resource_select=["type==RHEL8_64"])
        result = _merge_lsf(base, {"resource_select": ["mem>4000"]})
        assert result.resource_select == ["type==RHEL8_64", "mem>4000"]

    def test_bsub_extra_accumulated(self):
        base = LsfConfig(bsub_extra=["-G", "dv_users"])
        result = _merge_lsf(base, {"bsub_extra": ["-W", "2:00"]})
        assert result.bsub_extra == ["-G", "dv_users", "-W", "2:00"]

    def test_string_list_coercion(self):
        """Single string value for list field gets wrapped."""
        base = LsfConfig()
        result = _merge_lsf(base, {"resource_select": "type==RHEL8_64"})
        assert result.resource_select == ["type==RHEL8_64"]


class TestMergeLayer:
    def test_type_from_default(self):
        cfg = RunnerConfig()
        layer = {"runner": {"default": "lsf"}}
        result = _merge_layer(cfg, layer)
        assert result.type == "lsf"

    def test_type_from_type_key(self):
        cfg = RunnerConfig()
        layer = {"runner": {"type": "lsf"}}
        result = _merge_layer(cfg, layer)
        assert result.type == "lsf"

    def test_pool_config(self):
        cfg = RunnerConfig()
        layer = {"runner": {"pool": {"max_workers": 32, "idle_timeout": 600}}}
        result = _merge_layer(cfg, layer)
        assert result.pool.max_workers == 32
        assert result.pool.idle_timeout == 600
        assert result.pool.min_workers == 0  # unchanged

    def test_lsf_merge(self):
        cfg = RunnerConfig()
        layer = {"runner": {"lsf": {"queue": "regr_high", "bsub_cmd": "lsf_bsub"}}}
        result = _merge_layer(cfg, layer)
        assert result.lsf.queue == "regr_high"
        assert result.lsf.bsub_cmd == "lsf_bsub"

    def test_resource_classes(self):
        cfg = RunnerConfig()
        layer = {"runner": {"resource_classes": {
            "small": {"cores": 1, "memory": "2G"},
            "large": {"cores": 8, "memory": "32G"},
        }}}
        result = _merge_layer(cfg, layer)
        assert "small" in result.resource_classes
        assert result.resource_classes["large"].cores == 8

    def test_defaults_merge(self):
        cfg = RunnerConfig()
        layer = {"runner": {"defaults": {"memory": "4G", "cores": 2}}}
        result = _merge_layer(cfg, layer)
        assert result.defaults.memory == "4G"
        assert result.defaults.cores == 2
        assert result.defaults.walltime == "1:00"  # unchanged


class TestLoadRunnerConfig:
    def test_no_config_files(self, tmp_path, monkeypatch):
        """With no config files, defaults are used."""
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(project_root=str(tmp_path))
        assert cfg.type == "local"

    def test_install_config(self, tmp_path, monkeypatch):
        install_cfg = tmp_path / "install.yaml"
        install_cfg.write_text(yaml.dump({
            "runner": {
                "default": "lsf",
                "lsf": {"bsub_cmd": "lsf_bsub", "resource_select": ["type==RHEL8_64"]},
            }
        }))
        monkeypatch.setenv("DFM_INSTALL_CONFIG", str(install_cfg))
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(project_root=str(tmp_path))
        assert cfg.type == "lsf"
        assert cfg.lsf.bsub_cmd == "lsf_bsub"
        assert "type==RHEL8_64" in cfg.lsf.resource_select

    def test_project_overrides_install(self, tmp_path, monkeypatch):
        # Install config
        install_cfg = tmp_path / "install.yaml"
        install_cfg.write_text(yaml.dump({
            "runner": {"lsf": {"queue": "normal", "resource_select": ["type==RHEL8_64"]}}
        }))
        monkeypatch.setenv("DFM_INSTALL_CONFIG", str(install_cfg))
        monkeypatch.delenv("DFM_RUNNER", raising=False)

        # Project config
        proj = tmp_path / "proj"
        proj.mkdir()
        dfm_dir = proj / ".dfm"
        dfm_dir.mkdir()
        proj_cfg = dfm_dir / "config.yaml"
        proj_cfg.write_text(yaml.dump({
            "runner": {"lsf": {"queue": "regr_high", "resource_select": ["mem>4000"]}}
        }))

        cfg = load_runner_config(project_root=str(proj))
        # queue: last-writer-wins (project wins)
        assert cfg.lsf.queue == "regr_high"
        # resource_select: accumulated
        assert "type==RHEL8_64" in cfg.lsf.resource_select
        assert "mem>4000" in cfg.lsf.resource_select

    def test_env_var_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.setenv("DFM_RUNNER", "lsf")
        cfg = load_runner_config(project_root=str(tmp_path))
        assert cfg.type == "lsf"

    def test_cli_runner_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(
            project_root=str(tmp_path), cli_runner="lsf"
        )
        assert cfg.type == "lsf"

    def test_cli_opts(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(
            project_root=str(tmp_path),
            cli_opts={"queue": "regr_high", "project": "nbio-pcie"},
        )
        assert cfg.lsf.queue == "regr_high"
        assert cfg.lsf.project == "nbio-pcie"

    def test_bsub_cmd_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(project_root=str(tmp_path))
        assert cfg.lsf.bsub_cmd == "bsub"

    def test_bsub_cmd_overridden_by_install(self, tmp_path, monkeypatch):
        install_cfg = tmp_path / "install.yaml"
        install_cfg.write_text(yaml.dump({
            "runner": {"lsf": {"bsub_cmd": "lsf_bsub"}}
        }))
        monkeypatch.setenv("DFM_INSTALL_CONFIG", str(install_cfg))
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(project_root=str(tmp_path))
        assert cfg.lsf.bsub_cmd == "lsf_bsub"

    def test_project_field_inherited_from_site_overridden(self, tmp_path, monkeypatch):
        """project from site can be overridden by project config."""
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        # We can't easily test site config without mocking home dir,
        # but we can test layer merging directly
        cfg = RunnerConfig()
        site_layer = {"runner": {"lsf": {"project": "nbio"}}}
        cfg = _merge_layer(cfg, site_layer)
        assert cfg.lsf.project == "nbio"
        proj_layer = {"runner": {"lsf": {"project": "nbio-pcie"}}}
        cfg = _merge_layer(cfg, proj_layer)
        assert cfg.lsf.project == "nbio-pcie"

    def test_missing_files_produce_defaults(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DFM_INSTALL_CONFIG", raising=False)
        monkeypatch.delenv("DFM_RUNNER", raising=False)
        cfg = load_runner_config(project_root=str(tmp_path / "nonexistent"))
        assert cfg.type == "local"
        assert cfg.lsf.bsub_cmd == "bsub"
