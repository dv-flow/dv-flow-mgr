#****************************************************************************
#* test_set_parse.py
#*
#* Phase 1 of the `set:` scoped-overrides feature: parse + validate the `set:`
#* surface on TaskDef. No graph-build behavior yet — see
#* docs/proposals/set_overrides_impl_plan.md Phase 1.
#****************************************************************************
import pytest
from dv_flow.mgr.task_def import TaskDef


def _td(d):
    d = dict(d)
    d.setdefault("name", "T")
    return TaskDef.model_validate(d)


# ---- accept: well-formed shapes -------------------------------------------

def test_assignment_map_item():
    t = _td({"set": [{"hdlsim.sim": "mti", "opt": "-O3"}]})
    assert t.set_defs == [{"hdlsim.sim": "mti", "opt": "-O3"}]


def test_scope_item_with_uses():
    t = _td({"set": [{"uses": "hdlsim.*", "set": [{"sim": "mti"}]}]})
    assert t.set_defs[0]["uses"] == "hdlsim.*"
    assert t.set_defs[0]["set"] == [{"sim": "mti"}]


def test_scope_item_with_path():
    t = _td({"set": [{"path": "regress/**", "set": [{"opt": "-O0"}]}]})
    assert t.set_defs[0]["path"] == "regress/**"


def test_scope_item_with_uses_and_path():
    t = _td({"set": [{"uses": "hdlsim.*", "path": "smoke/**", "set": [{"sim": "xcm"}]}]})
    assert t.set_defs[0]["uses"] == "hdlsim.*"
    assert t.set_defs[0]["path"] == "smoke/**"


def test_nested_scope_items():
    t = _td({"set": [
        {"uses": "hdlsim.*", "set": [
            {"path": "smoke/**", "set": [{"sim": "xcm"}]}]}]})
    inner = t.set_defs[0]["set"][0]
    assert inner["path"] == "smoke/**"
    assert inner["set"] == [{"sim": "xcm"}]


def test_mixed_list_assignment_and_scoped():
    # The §R2.3 example verbatim.
    t = _td({"set": [
        {"hdlsim.sim": "mti"},
        {"uses": "hdlsim.*", "set": [{"sim": "mti"}]}]})
    assert len(t.set_defs) == 2
    assert "hdlsim.sim" in t.set_defs[0]
    assert t.set_defs[1]["uses"] == "hdlsim.*"


def test_empty_set_omitted_by_default():
    t = _td({"run": "echo hi"})
    assert t.set_defs == []


# ---- alias: provide -------------------------------------------------------

def test_provide_alias_folds_into_set():
    t = _td({"provide": [{"a.b": 1}]})
    assert t.set_defs == [{"a.b": 1}]


def test_provide_and_set_conflict():
    with pytest.raises(Exception):
        _td({"set": [{"a.b": 1}], "provide": [{"c": 2}]})


# ---- reject: malformed shapes ---------------------------------------------

def test_reject_set_not_a_list():
    with pytest.raises(Exception):
        _td({"set": "notalist"})


def test_reject_non_dict_element():
    with pytest.raises(Exception):
        _td({"set": ["notadict"]})


def test_reject_non_string_uses():
    with pytest.raises(Exception):
        _td({"set": [{"uses": 123, "set": []}]})


def test_reject_non_string_path():
    with pytest.raises(Exception):
        _td({"set": [{"path": ["x"], "set": []}]})


def test_reject_unexpected_key_in_scope_item():
    with pytest.raises(Exception) as ei:
        _td({"set": [{"set": [], "bogus": 1}]})
    assert "bogus" in str(ei.value)


def test_reserved_set_key_as_param_diagnosed():
    # A dict with a `set` key whose value is NOT a list is treated as a misuse:
    # `set` is reserved for nested scope items; a param may not be named `set`.
    with pytest.raises(Exception) as ei:
        _td({"set": [{"set": "vlt"}]})
    assert "reserved" in str(ei.value).lower() or "set" in str(ei.value).lower()


# ---- legacy let: still parses unchanged -----------------------------------

def test_legacy_let_still_parses():
    t = _td({"let": {"sim": "vlt"}})
    assert t.let == {"sim": "vlt"}
    assert t.set_defs == []
