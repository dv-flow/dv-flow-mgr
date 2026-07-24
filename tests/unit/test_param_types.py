"""
Unit tests for the canonical parameter-type model (param_types.py).

Covers normalize_type() across every declared-type representation and
coerce_to_kind() across the LIST/MAP/STR/scalar/ANY coercion matrix.

See docs/proposals/typed_param_expansion.md (§5.0, §5.2, §7).
"""
import typing
from typing import Any, Dict, List, Union

import pytest

from dv_flow.mgr.param_types import (
    TypeKind, ParamTypeError, normalize_type, coerce_to_kind,
)


# ---------------------------------------------------------------------------
# normalize_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kw,expect", [
    ("str", TypeKind.STR),
    ("int", TypeKind.INT),
    ("float", TypeKind.FLOAT),
    ("bool", TypeKind.BOOL),
    ("list", TypeKind.LIST),
    ("map", TypeKind.MAP),
    ("any", TypeKind.ANY),
    ("LIST", TypeKind.LIST),      # case-insensitive
    ("  list  ", TypeKind.LIST),  # whitespace-tolerant
    ("bogus", TypeKind.ANY),      # unknown keyword -> ANY
])
def test_normalize_keyword(kw, expect):
    assert normalize_type(kw) == expect


@pytest.mark.parametrize("pytype,expect", [
    (str, TypeKind.STR),
    (int, TypeKind.INT),
    (float, TypeKind.FLOAT),
    (bool, TypeKind.BOOL),
    (list, TypeKind.LIST),
    (dict, TypeKind.MAP),
])
def test_normalize_python_types(pytype, expect):
    assert normalize_type(pytype) == expect


def test_normalize_bool_before_int():
    # bool is a subclass of int; must resolve to BOOL, not INT
    assert normalize_type(bool) == TypeKind.BOOL


@pytest.mark.parametrize("ann,expect", [
    (Union[str, List], TypeKind.LIST),      # the dfm list encoding (ptype_m)
    (Union[str, Dict], TypeKind.MAP),        # the dfm map encoding
    (List, TypeKind.LIST),
    (List[Any], TypeKind.LIST),
    (List[str], TypeKind.LIST),
    (Dict, TypeKind.MAP),
    (Dict[str, Any], TypeKind.MAP),
    (typing.Optional[str], TypeKind.STR),    # Union[str, None] -> STR
    (typing.Optional[List], TypeKind.LIST),
    (Union[int, str], TypeKind.ANY),         # mixed scalar union -> ANY
])
def test_normalize_typing_constructs(ann, expect):
    assert normalize_type(ann) == expect


@pytest.mark.parametrize("t", [None, type(None), Any, object()])
def test_normalize_unknown_is_any(t):
    # None / NoneType / bare Any / unrecognized objects -> ANY, never NoneType
    assert normalize_type(t) == TypeKind.ANY


def test_normalize_typekind_passthrough():
    for k in TypeKind:
        assert normalize_type(k) is k


def test_normalize_complex_type_duck_typed():
    class ListType:  # stand-ins mirroring param_def.ComplexType shape
        pass

    class ComplexType:
        def __init__(self, list=None, map=None):
            self.list = list
            self.map = map

    assert normalize_type(ComplexType(list=ListType())) == TypeKind.LIST
    assert normalize_type(ComplexType(map=object())) == TypeKind.MAP
    assert normalize_type(ComplexType()) == TypeKind.ANY


# ---------------------------------------------------------------------------
# coerce_to_kind
# ---------------------------------------------------------------------------

def test_coerce_list_passthrough():
    v = ["a.sv", "b.sv"]
    assert coerce_to_kind(v, TypeKind.LIST) == v


def test_coerce_scalar_passes_through_to_list():
    # list == Union[str, List]: a bare string stays a string (downstream may
    # split it on whitespace). Never wrapped into a single-element list.
    assert coerce_to_kind("hvl_top", TypeKind.LIST) == "hvl_top"
    assert coerce_to_kind("a b c", TypeKind.LIST) == "a b c"
    assert coerce_to_kind(5, TypeKind.LIST) == 5


def test_coerce_none_to_list_is_empty():
    assert coerce_to_kind(None, TypeKind.LIST) == []


def test_coerce_map_into_list_errors():
    with pytest.raises(ParamTypeError):
        coerce_to_kind({"k": "v"}, TypeKind.LIST)


def test_coerce_map_passthrough():
    v = {"k": "v"}
    assert coerce_to_kind(v, TypeKind.MAP) == v


def test_coerce_none_to_map_is_empty():
    assert coerce_to_kind(None, TypeKind.MAP) == {}


@pytest.mark.parametrize("ok", ["scalar", 3])
def test_coerce_scalar_passes_through_to_map(ok):
    # map == Union[str, Dict]: a bare string/scalar is an accepted alternate form.
    assert coerce_to_kind(ok, TypeKind.MAP) == ok


def test_coerce_list_into_map_errors():
    with pytest.raises(ParamTypeError):
        coerce_to_kind(["x"], TypeKind.MAP)


def test_coerce_str_stringifies_containers():
    assert coerce_to_kind(["x"], TypeKind.STR) == '["x"]'
    assert coerce_to_kind({"k": "v"}, TypeKind.STR) == '{"k": "v"}'


def test_coerce_str_of_scalar():
    assert coerce_to_kind(5, TypeKind.STR) == "5"
    assert coerce_to_kind(None, TypeKind.STR) == ""


def test_coerce_scalar_kinds_passthrough_for_pydantic():
    # str values into int/float/bool slots pass through untouched so the
    # caller's scalar conversion / pydantic can validate them.
    assert coerce_to_kind("5", TypeKind.INT) == "5"
    assert coerce_to_kind("true", TypeKind.BOOL) == "true"
    assert coerce_to_kind("1.5", TypeKind.FLOAT) == "1.5"


def test_coerce_container_into_scalar_errors():
    with pytest.raises(ParamTypeError):
        coerce_to_kind(["x"], TypeKind.INT)
    with pytest.raises(ParamTypeError):
        coerce_to_kind({"k": "v"}, TypeKind.BOOL)


@pytest.mark.parametrize("v", [["x"], {"k": "v"}, "s", 3, None, True])
def test_coerce_any_is_exact_passthrough(v):
    assert coerce_to_kind(v, TypeKind.ANY) is v


def test_param_type_error_carries_srcinfo():
    sentinel = object()
    with pytest.raises(ParamTypeError) as ei:
        coerce_to_kind({"k": "v"}, TypeKind.LIST, srcinfo=sentinel)
    assert ei.value.srcinfo is sentinel
