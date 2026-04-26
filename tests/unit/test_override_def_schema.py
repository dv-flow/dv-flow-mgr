"""Tests for OverrideDef schema validation (Phase 2)."""
import pytest
from dv_flow.mgr.config_def import OverrideDef


def test_task_override_parses():
    """task: + with: parses correctly."""
    od = OverrideDef.model_validate({"task": "foo.Bar", "with": "baz.Qux"})
    assert od.task == "foo.Bar"
    assert od.value == "baz.Qux"
    assert od.package is None
    assert od.target_task == "foo.Bar"


def test_package_override_parses():
    """package: + with: parses correctly."""
    od = OverrideDef.model_validate({"package": "foo", "with": "bar"})
    assert od.package == "foo"
    assert od.value == "bar"
    assert od.task is None
    assert od.target_task is None


def test_both_task_and_package_error():
    """Setting both task and package raises validation error."""
    with pytest.raises(Exception, match="Only one"):
        OverrideDef.model_validate(
            {"task": "foo.Bar", "package": "foo", "with": "baz.Qux"}
        )


def test_neither_task_nor_package_error():
    """Setting neither task nor package (and no legacy override) raises validation error."""
    with pytest.raises(Exception, match="One of"):
        OverrideDef.model_validate({"with": "baz.Qux"})


def test_legacy_override_field():
    """Legacy 'override' field still works for backward compatibility."""
    od = OverrideDef.model_validate({"override": "foo.Bar", "with": "baz.Qux"})
    assert od.override == "foo.Bar"
    assert od.value == "baz.Qux"
    assert od.target_task == "foo.Bar"
