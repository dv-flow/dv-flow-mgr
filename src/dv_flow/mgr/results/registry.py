#****************************************************************************
#* registry.py -- the std metric-name registry
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
"""The std metric-name registry (``std/result_metrics.yaml``): the unit,
direction (``better``), roll-up rule and label for common metric names, so
producers in different libraries name and describe the same quantity the
same way."""
import os
from functools import lru_cache

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "std", "result_metrics.yaml")


@lru_cache(maxsize=1)
def registry():
    """``{name: {unit, better, rollup, label}}``."""
    if not os.path.isfile(_PATH):
        return {}
    import yaml
    with open(_PATH) as fp:
        doc = yaml.safe_load(fp) or {}
    ret = {}
    for ent in doc.get("metrics", []) or []:
        ret[ent["name"]] = {k: v for k, v in ent.items() if k != "name"}
    return ret


def lookup(name):
    """The registry entry for ``name``. ``cov_<kind>_pct`` style families are
    listed with a ``*`` wildcard (``cov_*_pct``)."""
    reg = registry()
    if name in reg:
        return reg[name]
    import fnmatch
    for k, v in reg.items():
        if "*" in k and fnmatch.fnmatchcase(name, k):
            return v
    return None
