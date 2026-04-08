"""Tests for resource_resolver: resolving ResourceReq from tags + config."""
import pytest
from dv_flow.mgr.resource_resolver import (
    resolve_resources, _extract_resource_tag, _parse_walltime,
)
from dv_flow.mgr.runner_config import (
    RunnerConfig, LsfConfig, ResourceDefaults, ResourceClassDef,
)
from dv_flow.mgr.runner_backend import ResourceReq


class TestParseWalltime:
    def test_hhmm(self):
        assert _parse_walltime("2:30") == 150

    def test_minutes_only(self):
        assert _parse_walltime("45") == 45

    def test_empty_returns_default(self):
        assert _parse_walltime("") == 60

    def test_invalid_returns_default(self):
        assert _parse_walltime("abc") == 60


class TestExtractResourceTag:
    def test_no_tags(self):
        assert _extract_resource_tag([]) is None
        assert _extract_resource_tag(None) is None

    def test_string_tag(self):
        result = _extract_resource_tag(["std.ResourceTag"])
        assert result == {}

    def test_dict_tag(self):
        result = _extract_resource_tag([{"std.ResourceTag": {"cores": 4}}])
        assert result == {"cores": 4}

    def test_other_tags_ignored(self):
        result = _extract_resource_tag(["std.AgentSkillTag", "std.Tag"])
        assert result is None

    def test_mixed_tags(self):
        result = _extract_resource_tag([
            "std.AgentSkillTag",
            {"std.ResourceTag": {"memory": "8G"}},
        ])
        assert result == {"memory": "8G"}


class TestResolveResources:
    def test_no_tag_uses_config_defaults(self):
        cfg = RunnerConfig(
            defaults=ResourceDefaults(cores=2, memory="4G", walltime="2:00"),
            lsf=LsfConfig(queue="default_q", project="proj1"),
        )
        req = resolve_resources([], cfg)
        assert req.cores == 2
        assert req.memory == "4G"
        assert req.queue == "default_q"
        assert req.project == "proj1"
        assert req.walltime_minutes == 120

    def test_explicit_cores_memory(self):
        cfg = RunnerConfig()
        req = resolve_resources(
            [{"std.ResourceTag": {"cores": 4, "memory": "8G"}}], cfg
        )
        assert req.cores == 4
        assert req.memory == "8G"

    def test_explicit_queue_from_tag(self):
        cfg = RunnerConfig(lsf=LsfConfig(queue="default_q"))
        req = resolve_resources(
            [{"std.ResourceTag": {"queue": "sim_queue"}}], cfg
        )
        assert req.queue == "sim_queue"

    def test_resource_class_lookup(self):
        cfg = RunnerConfig(
            resource_classes={
                "large": ResourceClassDef(cores=8, memory="32G"),
            }
        )
        req = resolve_resources(
            [{"std.ResourceTag": {"resource_class": "large"}}], cfg
        )
        assert req.cores == 8
        assert req.memory == "32G"

    def test_unknown_resource_class_raises(self):
        cfg = RunnerConfig()
        with pytest.raises(ValueError, match="Unknown resource class"):
            resolve_resources(
                [{"std.ResourceTag": {"resource_class": "nonexistent"}}], cfg
            )

    def test_resource_class_queue_override(self):
        cfg = RunnerConfig(
            lsf=LsfConfig(queue="default_q"),
            resource_classes={
                "gpu": ResourceClassDef(cores=4, memory="16G", queue="gpu_queue"),
            },
        )
        req = resolve_resources(
            [{"std.ResourceTag": {"resource_class": "gpu"}}], cfg
        )
        assert req.queue == "gpu_queue"

    def test_resource_class_resource_select_merged(self):
        cfg = RunnerConfig(
            lsf=LsfConfig(resource_select=["type==RHEL8_64"]),
            resource_classes={
                "gpu": ResourceClassDef(
                    cores=4, memory="16G",
                    resource_select=["ngpus>0"],
                ),
            },
        )
        req = resolve_resources(
            [{"std.ResourceTag": {"resource_class": "gpu"}}], cfg
        )
        assert "type==RHEL8_64" in req.resource_select
        assert "ngpus>0" in req.resource_select

    def test_project_from_config_not_tag(self):
        """project always comes from LsfConfig, not from the tag."""
        cfg = RunnerConfig(lsf=LsfConfig(project="nbio-pcie"))
        req = resolve_resources(
            [{"std.ResourceTag": {"cores": 2}}], cfg
        )
        assert req.project == "nbio-pcie"

    def test_walltime_from_tag(self):
        cfg = RunnerConfig()
        req = resolve_resources(
            [{"std.ResourceTag": {"walltime": "4:00"}}], cfg
        )
        assert req.walltime_minutes == 240

    def test_config_defaults_override_resource_req_defaults(self):
        """Config defaults should override ResourceReq built-in defaults."""
        cfg = RunnerConfig(
            defaults=ResourceDefaults(memory="4G", cores=2, walltime="2:00"),
        )
        req = resolve_resources([], cfg)
        assert req.memory == "4G"
        assert req.cores == 2
        assert req.walltime_minutes == 120
