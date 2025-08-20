import os
import tempfile
import yaml
from dv_flow.mgr.package_loader import PackageLoader

def test_strategy_matrix_loading():
    # Create a minimal package YAML with a strategy matrix
    pkg_yaml = {
        "package": {
            "name": "pkg",
            "tasks": [
                {
                    "name": "matrix_task",
                    "strategy": {
                        "matrix": {
                            "os": ["linux", "windows"],
                            "python": ["3.8", "3.9"]
                        }
                    }
                }
            ],
            "types": [],
            "fragments": [],
            "imports": [],
            "overrides": {}
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = os.path.join(tmpdir, "flow.dv")
        with open(pkg_path, "w") as f:
            yaml.dump(pkg_yaml, f)
        loader = PackageLoader()
        pkg = loader.load(pkg_path)
        task = pkg.task_m["pkg.matrix_task"]
        assert task.strategy is not None
        assert task.strategy.matrix == {
            "os": ["linux", "windows"],
            "python": ["3.8", "3.9"]
        }
