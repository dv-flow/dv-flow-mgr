#****************************************************************************
#* runner_config.py
#*
#* Layered runner configuration: install -> site -> user -> project -> env/CLI.
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
#*
#****************************************************************************
import dataclasses as dc
import logging
import os
import sys
from typing import Any, ClassVar, Dict, List, Optional

import yaml

from . import config_paths


_log = logging.getLogger("RunnerConfig")


@dc.dataclass
class LsfConfig:
    """LSF-specific runner configuration."""
    bsub_cmd: str = "bsub"
    queue: str = ""
    project: str = ""
    resource_select: List[str] = dc.field(default_factory=list)
    bsub_extra: List[str] = dc.field(default_factory=list)
    worker_dfm_path: str = "dfm"


@dc.dataclass
class ResourceClassDef:
    """Named resource class definition."""
    cores: int = 1
    memory: str = "1G"
    queue: str = ""
    resource_select: List[str] = dc.field(default_factory=list)


@dc.dataclass
class ResourceDefaults:
    """Default resource requirements for tasks."""
    memory: str = "1G"
    cores: int = 1
    walltime: str = "1:00"


@dc.dataclass
class PoolConfig:
    """Worker pool scaling parameters."""
    min_workers: int = 0
    max_workers: int = 16
    idle_timeout: int = 300
    launch_batch_size: int = 4


@dc.dataclass
class RunnerConfig:
    """Complete runner configuration assembled from all layers."""
    type: str = "local"
    pool: PoolConfig = dc.field(default_factory=PoolConfig)
    lsf: LsfConfig = dc.field(default_factory=LsfConfig)
    defaults: ResourceDefaults = dc.field(default_factory=ResourceDefaults)
    resource_classes: Dict[str, ResourceClassDef] = dc.field(default_factory=dict)


def _install_config_path() -> Optional[str]:
    """Resolve installation config path (DFM_INSTALL_CONFIG or
    <sys.prefix>/etc/dfm/config.yaml)."""
    return config_paths.install_config_path()


def _site_config_path() -> Optional[str]:
    """Deprecated: the legacy user-level ~/.config/dfm/site.yaml, if present.
    User config now lives in config.yaml (see config_paths)."""
    path = os.path.join(config_paths.user_config_dir(), "site.yaml")
    if os.path.isfile(path):
        return path
    return None


def _project_config_path(project_root: Optional[str] = None) -> Optional[str]:
    """Resolve project config path: <project>/.dfm/config.yaml."""
    path = config_paths.project_config_path(project_root)
    if os.path.isfile(path):
        return path
    return None


def _load_yaml(path: str) -> Dict[str, Any]:
    """Load a YAML file, returning empty dict if missing."""
    if path is None or not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            "Runner config file %s must contain a YAML mapping, got %s"
            % (path, type(data).__name__)
        )
    return data


def _merge_lsf(base: LsfConfig, overlay: Dict[str, Any]) -> LsfConfig:
    """Merge an overlay dict into LsfConfig.

    Scalar fields use last-writer-wins.
    List fields (resource_select, bsub_extra) are accumulated.
    """
    if not overlay:
        return base
    result = dc.replace(base)
    if "bsub_cmd" in overlay:
        result.bsub_cmd = overlay["bsub_cmd"]
    if "queue" in overlay:
        result.queue = overlay["queue"]
    if "project" in overlay:
        result.project = overlay["project"]
    # Accumulate list fields
    if "resource_select" in overlay:
        items = overlay["resource_select"]
        if isinstance(items, list):
            result.resource_select = result.resource_select + items
        elif isinstance(items, str):
            result.resource_select = result.resource_select + [items]
    if "bsub_extra" in overlay:
        items = overlay["bsub_extra"]
        if isinstance(items, list):
            result.bsub_extra = result.bsub_extra + items
        elif isinstance(items, str):
            result.bsub_extra = result.bsub_extra + [items]
    if "worker_dfm_path" in overlay:
        result.worker_dfm_path = overlay["worker_dfm_path"]
    return result


def _merge_resource_classes(
    base: Dict[str, ResourceClassDef],
    overlay: Dict[str, Any]
) -> Dict[str, ResourceClassDef]:
    """Merge resource class definitions (last-writer-wins per class name)."""
    if not overlay:
        return base
    result = dict(base)
    for name, defn in overlay.items():
        if isinstance(defn, dict):
            result[name] = ResourceClassDef(
                cores=defn.get("cores", 1),
                memory=defn.get("memory", "1G"),
                queue=defn.get("queue", ""),
                resource_select=defn.get("resource_select", []),
            )
    return result


def _merge_layer(config: RunnerConfig, layer: Dict[str, Any]) -> RunnerConfig:
    """Merge a single config layer (dict from YAML) into RunnerConfig."""
    runner = layer.get("runner", layer)
    if not isinstance(runner, dict):
        return config

    result = dc.replace(config)

    # Runner type: last-writer-wins
    if "default" in runner:
        result.type = runner["default"]
    if "type" in runner:
        result.type = runner["type"]

    # Pool config
    pool_data = runner.get("pool", {})
    if pool_data:
        result.pool = dc.replace(
            result.pool,
            min_workers=pool_data.get("min_workers", result.pool.min_workers),
            max_workers=pool_data.get("max_workers", result.pool.max_workers),
            idle_timeout=pool_data.get("idle_timeout", result.pool.idle_timeout),
            launch_batch_size=pool_data.get(
                "launch_batch_size", result.pool.launch_batch_size
            ),
        )

    # LSF config (accumulated list fields)
    lsf_data = runner.get("lsf", {})
    if lsf_data:
        result.lsf = _merge_lsf(result.lsf, lsf_data)

    # Defaults
    defaults_data = runner.get("defaults", {})
    if defaults_data:
        result.defaults = dc.replace(
            result.defaults,
            memory=defaults_data.get("memory", result.defaults.memory),
            cores=defaults_data.get("cores", result.defaults.cores),
            walltime=defaults_data.get("walltime", result.defaults.walltime),
        )

    # Resource classes
    rc_data = runner.get("resource_classes", {})
    if rc_data:
        result.resource_classes = _merge_resource_classes(
            result.resource_classes, rc_data
        )

    return result


def load_runner_config(
    project_root: Optional[str] = None,
    cli_runner: Optional[str] = None,
    cli_opts: Optional[Dict[str, str]] = None,
) -> RunnerConfig:
    """Load and merge runner configuration from all layers.

    Merge order (later overrides earlier):
      1. Built-in defaults
      2. Installation config (<prefix>/etc/dfm/config.yaml or DFM_INSTALL_CONFIG)
      3. Site config (/etc/dfm/config.yaml or DFM_SITE_CONFIG)
      4. User config (~/.config/dfm/config.yaml, legacy site.yaml, or
         DFM_USER_CONFIG)
      5. Project config (<project>/.dfm/config.yaml)
      6. Environment variable DFM_RUNNER
      7. CLI flags (--runner, --runner-opt)

    Returns:
        Fully merged RunnerConfig
    """
    config = RunnerConfig()

    # Layers: install, site (/etc/dfm), user (~/.config/dfm), project.
    # Later layers override earlier ones.
    for layer, path, data in config_paths.config_layers(project_root):
        if data:
            try:
                config = _merge_layer(config, data)
                _log.debug("Loaded %s config from %s", layer, path)
            except Exception as e:
                _log.warning("Failed to load %s config %s: %s", layer, path, e)

    # Layer 5: environment variable
    env_runner = os.environ.get("DFM_RUNNER")
    if env_runner:
        config.type = env_runner

    # Layer 6: CLI overrides
    if cli_runner:
        config.type = cli_runner
    if cli_opts:
        # Simple key=value overrides applied to top-level runner fields
        for key, value in cli_opts.items():
            if key == "queue":
                config.lsf.queue = value
            elif key == "project":
                config.lsf.project = value
            elif key == "bsub_cmd":
                config.lsf.bsub_cmd = value

    return config
