#****************************************************************************
#* config.py -- the `results:` section of the dfm config
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
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
"""The ``results:`` section of the dfm config files (installation, site,
then project ``.dfm/config.yaml``; a later file wins key by key)::

    results:
      keep_previous: 1    # earlier runs kept under rundir/out besides this
                          # one; 0 = only this run, all = never prune
      copy_logs: false    # copy role=log artifacts into out/<run-id>/logs/
      tree: true          # build the out/<run-id>/results/ link tree
      formats: []         # extra renderings next to results.json: junit, ctrf
      strict_roots: false # a root task without a Result in produces: is an error
      filter_roots: true  # a root that declares a Result passes on only Results

``DFM_RESULTS_FORMATS`` (comma-separated) and ``dfm run --results-format``
override ``formats`` for one run.
"""
import dataclasses as dc
import logging
import os
from typing import List, Optional

_log = logging.getLogger("results.config")

FORMATS = ("junit", "ctrf", "md")
FORMAT_FILES = {"junit": "junit.xml", "ctrf": "ctrf.json", "md": "summary.md"}
ENV_FORMATS = "DFM_RESULTS_FORMATS"


@dc.dataclass
class ResultsConfig:
    # Earlier run records kept besides the current one; None = never prune.
    keep_previous: Optional[int] = 1
    copy_logs: bool = False
    tree: bool = True
    formats: List[str] = dc.field(default_factory=list)
    strict_roots: bool = False
    filter_roots: bool = True


def parse_formats(values) -> List[str]:
    """``["junit,ctrf", "md"]`` -> ``["junit", "ctrf", "md"]``; unknown names
    raise ValueError."""
    ret = []
    for v in values or []:
        for f in str(v).split(","):
            f = f.strip().lower()
            if not f:
                continue
            if f not in FORMATS:
                raise ValueError("unknown results format '%s' (expected one of %s)"
                                 % (f, ", ".join(FORMATS)))
            if f not in ret:
                ret.append(f)
    return ret


def _apply(cfg: ResultsConfig, sect, path):
    if not isinstance(sect, dict):
        _log.warning("%s: 'results' must be a mapping; ignored" % path)
        return
    for k, v in sect.items():
        if k == "keep_previous":
            if str(v).strip().lower() == "all":
                cfg.keep_previous = None
                continue
            try:
                n = int(v)
                if n < 0:
                    raise ValueError()
                cfg.keep_previous = n
            except (TypeError, ValueError):
                _log.warning("%s: results.keep_previous must be a count >= 0 "
                             "or 'all'" % path)
        elif k == "keep":
            # The earlier spelling: a total, counting this run; 0 never pruned.
            try:
                n = int(v)
                cfg.keep_previous = None if n <= 0 else n - 1
                _log.warning("%s: results.keep is now results.keep_previous "
                             "(earlier runs kept besides this one); read "
                             "keep: %s as keep_previous: %s" % (
                                 path, v, "all" if n <= 0 else n - 1))
            except (TypeError, ValueError):
                _log.warning("%s: results.keep must be an integer" % path)
        elif k in ("copy_logs", "tree", "strict_roots", "filter_roots"):
            setattr(cfg, k, bool(v))
        elif k == "formats":
            try:
                cfg.formats = parse_formats(v if isinstance(v, list) else [v])
            except ValueError as e:
                _log.warning("%s: %s" % (path, e))
        else:
            _log.warning("%s: unknown key results.%s" % (path, k))


def load_results_config(project_root: Optional[str] = None) -> ResultsConfig:
    from ..runner_config import (_install_config_path, _site_config_path,
                                 _project_config_path, _load_yaml)
    cfg = ResultsConfig()
    for path in (_install_config_path(), _site_config_path(),
                 _project_config_path(project_root)):
        if not path:
            continue
        try:
            data = _load_yaml(path)
        except Exception as e:
            _log.warning("could not read %s: %s" % (path, e))
            continue
        if "results" in data:
            _apply(cfg, data["results"], path)
    env = os.environ.get(ENV_FORMATS)
    if env is not None:
        try:
            cfg.formats = parse_formats([env])
        except ValueError as e:
            _log.warning("%s: %s" % (ENV_FORMATS, e))
    return cfg
