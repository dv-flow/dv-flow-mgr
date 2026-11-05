"""Locations of dfm's layered YAML config files.

=========  ===========================================  =====================
Layer      Path                                         Override env var
=========  ===========================================  =====================
install    ``<sys.prefix>/etc/dfm/config.yaml``          ``DFM_INSTALL_CONFIG``
site       ``/etc/dfm/config.yaml``                      ``DFM_SITE_CONFIG``
user       ``$XDG_CONFIG_HOME/dfm/config.yaml``          ``DFM_USER_CONFIG``
           (legacy alias: ``.../dfm/site.yaml``)
project    ``<pkg_root>/.dfm/config.yaml``
=========  ===========================================  =====================
"""
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

_log = logging.getLogger("ConfigPaths")

_legacy_noted = False


def install_config_path() -> Optional[str]:
    env_path = os.environ.get("DFM_INSTALL_CONFIG")
    if env_path:
        return env_path
    prefix_path = os.path.join(sys.prefix, "etc", "dfm", "config.yaml")
    if os.path.isfile(prefix_path):
        return prefix_path
    return None


def site_config_path() -> Optional[str]:
    env_path = os.environ.get("DFM_SITE_CONFIG")
    if env_path:
        return env_path
    return "/etc/dfm/config.yaml"


def user_config_dir() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if not xdg:
        xdg = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(xdg, "dfm")


def user_config_paths() -> List[str]:
    """User config files, highest priority first. With ``DFM_USER_CONFIG``
    set, only that file is used. Otherwise ``config.yaml`` then the legacy
    ``site.yaml``."""
    env_path = os.environ.get("DFM_USER_CONFIG")
    if env_path:
        return [env_path]
    d = user_config_dir()
    return [os.path.join(d, "config.yaml"), os.path.join(d, "site.yaml")]


def project_config_path(project_root: Optional[str] = None) -> str:
    root = project_root or os.getcwd()
    return os.path.join(root, ".dfm", "config.yaml")


def load_yaml(path: Optional[str]) -> Dict[str, Any]:
    """Load a YAML mapping, returning {} if the file is missing or empty."""
    if path is None or not os.path.isfile(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Config file %s must contain a YAML mapping, got %s"
                         % (path, type(data).__name__))
    return data


def _note_legacy(site_yaml: str, have_config: bool):
    global _legacy_noted
    if _legacy_noted:
        return
    _legacy_noted = True
    msg = ("%s is deprecated; rename it to config.yaml in the same directory"
           % site_yaml)
    if have_config:
        _log.debug(msg)
    else:
        _log.info(msg)


def load_user_config() -> Tuple[Dict[str, Any], List[str]]:
    """Return the merged user-level config and the files it came from.

    ``config.yaml`` wins key-by-key (top-level) over the legacy ``site.yaml``.
    """
    paths = user_config_paths()
    data: Dict[str, Any] = {}
    used: List[str] = []
    for p in reversed(paths):
        if not os.path.isfile(p):
            continue
        layer = load_yaml(p)
        if os.path.basename(p) == "site.yaml" and len(paths) > 1:
            _note_legacy(p, os.path.isfile(paths[0]))
        data.update(layer)
        used.insert(0, p)
    return data, used


def config_layers(project_root: Optional[str] = None
                  ) -> List[Tuple[str, Optional[str], Dict[str, Any]]]:
    """All file layers as (layer-name, path, data), lowest priority first:
    install, site, user, project. Missing files yield {}; unreadable ones log
    a warning and yield {}."""
    ret = []

    def _safe(layer, path):
        try:
            return load_yaml(path)
        except Exception as e:
            _log.warning("Failed to load %s config %s: %s", layer, path, e)
            return {}

    ip = install_config_path()
    ret.append(("install", ip, _safe("install", ip)))
    sp = site_config_path()
    ret.append(("site", sp, _safe("site", sp)))
    try:
        ud, used = load_user_config()
    except Exception as e:
        _log.warning("Failed to load user config: %s", e)
        ud, used = {}, []
    ret.append(("user", used[0] if used else user_config_paths()[0], ud))
    pp = project_config_path(project_root)
    ret.append(("project", pp, _safe("project", pp)))
    return ret
