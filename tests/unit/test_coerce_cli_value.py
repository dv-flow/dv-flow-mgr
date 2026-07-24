"""Single CLI/-D coercion policy (param_types.coerce_cli_value).

Pins the unified behavior that replaced three divergent string->typed ladders
(F1/F2/F3 of docs/proposals/variable_handling_cleanup.md): comma-split for a
bare list string, TRUTHY bool, int base-0, with a strict/lenient int-failure
policy.
"""
import typing
import pytest
from dv_flow.mgr.param_types import coerce_cli_value, ParamTypeError, TypeKind


LIST_T = typing.Union[str, typing.List]
MAP_T = typing.Dict


def test_list_comma_split():
    assert coerce_cli_value("a,b,c", LIST_T) == ["a", "b", "c"]
    assert coerce_cli_value("a, b , c", LIST_T) == ["a", "b", "c"]  # trimmed


def test_list_single_value_is_singleton():
    # A no-comma string stays a single-element list (legacy simple case).
    assert coerce_cli_value("foo.sv", LIST_T) == ["foo.sv"]


def test_list_empty_string_is_empty_list():
    assert coerce_cli_value("", LIST_T) == []


def test_list_already_a_list_passthrough():
    assert coerce_cli_value(["a", "b"], LIST_T) == ["a", "b"]


def test_bool_truthy():
    assert coerce_cli_value("true", bool) is True
    assert coerce_cli_value("Yes", bool) is True
    assert coerce_cli_value("on", bool) is True
    assert coerce_cli_value("0", bool) is False
    assert coerce_cli_value("nope", bool) is False
    assert coerce_cli_value(True, bool) is True


def test_int_base0():
    assert coerce_cli_value("42", int) == 42
    assert coerce_cli_value("0x10", int) == 16
    assert coerce_cli_value(7, int) == 7


def test_int_strict_raises_lenient_defaults():
    assert coerce_cli_value("nan", int) == 0                 # lenient default
    with pytest.raises(ParamTypeError):
        coerce_cli_value("nan", int, strict=True)            # strict raises


def test_float():
    assert coerce_cli_value("3.5", float) == 3.5
    assert coerce_cli_value(2, float) == 2.0


def test_str():
    assert coerce_cli_value(5, str) == "5"
    assert coerce_cli_value("x", str) == "x"


def test_map_passthrough():
    assert coerce_cli_value({"a": 1}, MAP_T) == {"a": 1}


def test_unknown_type_passthrough():
    o = object()
    assert coerce_cli_value(o, None) is o
