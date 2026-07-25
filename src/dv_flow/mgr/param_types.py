#****************************************************************************
#* param_types.py
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
#* Created on:
#*     Author:
#*
#****************************************************************************
"""
Canonical parameter-type model for the expansion pipeline.

A parameter's declared type reaches the engine in several inconsistent shapes
(keyword strings like ``'list'``, the ``ptype_m`` Python encodings such as
``Union[str, List]``, ``ComplexType`` blocks, raw pydantic annotations, or
``None`` for an unresolved override). This module collapses all of them onto a
single :class:`TypeKind` and provides one deterministic coercion function so
value handling is identical at every expansion site.

The module is intentionally free of any ``dv_flow.mgr`` imports so it can be
unit-tested in isolation and reused anywhere in the pipeline. ``ComplexType`` is
recognized by duck-typing rather than an import to keep it dependency-free.

See ``docs/proposals/typed_param_expansion.md`` (§5.0, §5.2).
"""
import json
import typing
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union


class TypeKind(Enum):
    """The normalized kind of a parameter's declared type.

    ``ANY`` is the permissive floor: it is emitted for ``None``/unknown/unresolved
    types and means "pass the value through unchanged" — never a hard ``NoneType``
    that would reject every value at pydantic validation.
    """
    STR = auto()
    INT = auto()
    FLOAT = auto()
    BOOL = auto()
    LIST = auto()
    MAP = auto()
    ANY = auto()


class ParamTypeError(Exception):
    """A located type mismatch discovered during parameter coercion.

    Carries the offending ``with:`` entry's ``srcinfo`` (when available) so the
    error can be reported at the authoring site instead of surfacing later as a
    contextless pydantic failure.
    """
    def __init__(self, message: str, srcinfo: Any = None):
        super().__init__(message)
        self.srcinfo = srcinfo


class ParamValueError(ParamTypeError):
    """A value outside the parameter's declared value set.

    A subclass of :class:`ParamTypeError` so every site that already reports a
    located type problem reports this one the same way, with no new handling.
    """


_KEYWORD_KIND = {
    "str": TypeKind.STR,
    "int": TypeKind.INT,
    "float": TypeKind.FLOAT,
    "bool": TypeKind.BOOL,
    "list": TypeKind.LIST,
    "map": TypeKind.MAP,
    "any": TypeKind.ANY,
}


# Keyword type-name -> Python annotation used for a declared param's pydantic
# field. `list` is the dfm ``Union[str, List]`` encoding (a bare string is an
# accepted alternate form, split/parsed downstream); `map` is ``Dict``. Single
# source of truth for what was previously copied as ``ptype_m`` in several sites.
KEYWORD_TYPE = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": Union[str, List],
    "map": Dict,
}


# Tokens accepted as boolean-true for a string->bool coercion. Single source of
# truth for what was copied inline in a few coercion sites.
TRUTHY = frozenset(("1", "true", "yes", "y", "on"))


def keyword_default(kw: str):
    """Fresh per-kind empty default for a keyword type name (`str`->"",
    `list`->[], `map`->{}, ...). list/map return a NEW container each call so
    two declarations never share a mutable default. Replaces the copied
    ``pdflt_m`` tables."""
    return _kind_default(normalize_type(kw))


def _is_complex_type(t) -> bool:
    """Duck-type a ``param_def.ComplexType`` instance without importing it."""
    return (type(t).__name__ == "ComplexType"
            and hasattr(t, "list") and hasattr(t, "map"))


def normalize_type(t) -> TypeKind:
    """Collapse any declared-type representation onto a :class:`TypeKind`.

    Handles keyword strings, plain Python types, ``typing`` constructs (including
    the dfm list encoding ``Union[str, List]`` -> ``LIST`` and ``Union[str, Dict]``
    -> ``MAP``), ``ComplexType`` blocks, and ``TypeKind`` passthrough. ``None`` /
    ``NoneType`` / anything unrecognized -> ``ANY`` (never ``NoneType``).

    ``bool`` is checked before ``int`` because ``bool`` is a subclass of ``int``.
    """
    if t is None or t is type(None):
        return TypeKind.ANY

    if isinstance(t, TypeKind):
        return t

    # Keyword string ('list', 'map', 'str', ...)
    if isinstance(t, str):
        return _KEYWORD_KIND.get(t.strip().lower(), TypeKind.ANY)

    # ComplexType block: list/map presence decides the kind
    if _is_complex_type(t):
        if getattr(t, "list", None) is not None:
            return TypeKind.LIST
        if getattr(t, "map", None) is not None:
            return TypeKind.MAP
        return TypeKind.ANY

    # Plain Python types -- bool BEFORE int (bool is an int subclass)
    if t is bool:
        return TypeKind.BOOL
    if t is int:
        return TypeKind.INT
    if t is float:
        return TypeKind.FLOAT
    if t is str:
        return TypeKind.STR
    if t is list or t is typing.List:
        return TypeKind.LIST
    if t is dict or t is typing.Dict:
        return TypeKind.MAP
    if t is Any:
        return TypeKind.ANY

    # typing constructs: List[...], Dict[...], Union[...]
    origin = typing.get_origin(t)
    if origin is not None:
        if origin is list:
            return TypeKind.LIST
        if origin is dict:
            return TypeKind.MAP
        if origin is typing.Union:
            args = [a for a in typing.get_args(t) if a is not type(None)]
            kinds = [normalize_type(a) for a in args]
            # The dfm list/map encodings are Unions that include a container.
            if TypeKind.LIST in kinds:
                return TypeKind.LIST
            if TypeKind.MAP in kinds:
                return TypeKind.MAP
            unique = set(kinds)
            if len(unique) == 1:
                return next(iter(unique))
            return TypeKind.ANY

    return TypeKind.ANY


# Per-kind "empty" default. Used when a typed slot receives an empty/None value
# instead of erroring; also backs the public keyword_default() accessor.
_KIND_DEFAULT = {
    TypeKind.STR: "",
    TypeKind.INT: 0,
    TypeKind.FLOAT: 0.0,
    TypeKind.BOOL: False,
    TypeKind.LIST: list,   # factory sentinels; instantiated in coerce_to_kind
    TypeKind.MAP: dict,
}


def _kind_default(kind: TypeKind):
    d = _KIND_DEFAULT.get(kind)
    if d is list:
        return []
    if d is dict:
        return {}
    return d


def coerce_to_kind(value, kind: TypeKind, *, srcinfo: Any = None) -> Any:
    """Coerce an already-evaluated value to the destination ``kind``.

    The dfm encodings ``list == Union[str, List]`` and ``map == Union[str, Dict]``
    mean **a bare string is always an accepted alternate form** of a list/map:
    downstream callables (e.g. ``std.FileSet``) split a space-separated string
    into a list. So coercion must NOT wrap or reject strings for a container
    destination — it only rejects a *different* container (a map into a list, or a
    list into a map), which is a genuine mismatch. Preserving a native list's type
    (the Mode A fix) is the job of the whole-value ``eval_obj`` path, not this
    function; here a list simply passes through unchanged.

    Scalar kinds defer str->scalar conversion to the caller / pydantic; ``ANY`` is
    exact legacy passthrough. Genuine mismatches raise :class:`ParamTypeError`
    citing ``srcinfo``.

    Table (see proposal §5.2):

    ===== =========== ============ =================== =========
    dst   list value  map value    scalar/str value    None
    ===== =========== ============ =================== =========
    LIST  pass        **error**    pass (may split)    ``[]``
    MAP   **error**   pass         pass (may parse)    ``{}``
    STR   json.dumps  json.dumps   ``str(value)``      ``""``
    INT/  error       error        passthrough         default
    FLOAT/                         (pydantic converts)
    BOOL
    ANY   pass        pass         pass                pass
    ===== =========== ============ =================== =========
    """
    if kind is TypeKind.ANY:
        return value

    is_list = isinstance(value, list)
    # bool is an int subclass, but for container/mapping tests only dict matters
    is_map = isinstance(value, dict)

    if kind is TypeKind.LIST:
        if value is None:
            return []
        if is_map:
            raise ParamTypeError(
                "cannot assign a map value to a list-typed parameter", srcinfo)
        # list -> passthrough; str/scalar -> passthrough (union allows it, and a
        # space-separated string may be split downstream). Never wrap.
        return value

    if kind is TypeKind.MAP:
        if value is None:
            return {}
        if is_list:
            raise ParamTypeError(
                "cannot assign a list value to a map-typed parameter", srcinfo)
        # dict -> passthrough; str/scalar -> passthrough (union allows it).
        return value

    if kind is TypeKind.STR:
        if value is None:
            return ""
        if is_list or is_map:
            return json.dumps(value)
        return str(value)

    # INT / FLOAT / BOOL scalar kinds
    if value is None:
        return _kind_default(kind)
    if is_list or is_map:
        raise ParamTypeError(
            "cannot assign a %s value to a %s-typed parameter" % (
                "list" if is_list else "map", kind.name.lower()), srcinfo)
    # Let the caller's scalar conversion / pydantic handle str->int/float/bool.
    return value


def coerce_cli_value(value, t, *, strict: bool = False, srcinfo: Any = None):
    """Coerce a raw command-line / ``-D`` / ``set:``-forced value to the declared
    type ``t``. This is the SINGLE policy for how an out-of-band (usually string)
    value becomes a typed parameter value — replacing the several hand-rolled
    int/float/bool/str/list ladders that had drifted apart:

      * ``list``  -> a bare string is **comma-split** (``"a,b"`` -> ``["a","b"]``,
                     ``""`` -> ``[]``); an already-parsed list passes through.
                     (A no-comma string yields a single-element list, so simple
                     ``include=foo.sv`` -> ``["foo.sv"]`` is unchanged.)
      * ``map``   -> passed through (must already be a parsed mapping).
      * ``bool``  -> :data:`TRUTHY`-token test.
      * ``int``   -> ``int(str(v), 0)`` (accepts 0x/0o bases); ``float`` similarly.
      * ``str``   -> ``str(value)``.
      * ``any`` / unknown -> value unchanged.

    ``strict`` controls the int/float parse-failure policy: strict raises
    :class:`ParamTypeError` (task-param ``-D`` — fail loudly), non-strict returns
    the per-kind zero default (package-var ``-D`` — lenient, legacy behavior).
    """
    kind = normalize_type(t)

    if kind is TypeKind.LIST:
        if isinstance(value, list):
            return value
        s = str(value).strip() if value is not None else ""
        return [e.strip() for e in s.split(",") if e.strip()] if s else []

    if kind is TypeKind.MAP:
        return value

    if kind is TypeKind.BOOL:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in TRUTHY

    if kind in (TypeKind.INT, TypeKind.FLOAT):
        want_int = kind is TypeKind.INT
        if isinstance(value, bool):
            value = int(value)
        if want_int and isinstance(value, int):
            return value
        if not want_int and isinstance(value, (int, float)):
            return float(value)
        try:
            return int(str(value), 0) if want_int else float(str(value))
        except (ValueError, TypeError):
            if strict:
                raise ParamTypeError(
                    "cannot convert %r to %s" % (value, kind.name.lower()),
                    srcinfo)
            return _kind_default(kind)

    if kind is TypeKind.STR:
        return value if isinstance(value, str) else str(value)

    return value


#---------------------------------------------------------------------------
# Value sets
#
# A parameter may declare the values it accepts (`values:` on its ParamDef).
# This is the single enforcement policy, called from every site that can set a
# parameter: the declaration/`uses:`-override pass, `-D`, a task's own `--flag`,
# and package vars. Duck-typed against `param_def.ValueSet` so this module stays
# free of dv_flow.mgr imports (see the module docstring).
#---------------------------------------------------------------------------

def value_set_members(valueset) -> Tuple[List[Any], bool]:
    """(members, is_open) for a ValueSet-like object or a plain list."""
    if valueset is None:
        return [], False
    of = getattr(valueset, "of", None)
    if of is None:
        if isinstance(valueset, (list, tuple)):
            return list(valueset), False
        return [], False
    members = [getattr(e, "value", e) for e in of]
    return members, bool(getattr(valueset, "open", False))


def _member_of(value, members) -> bool:
    """Exact membership. `bool` is compared only against `bool`, because
    `True == 1` would otherwise make a boolean a member of any set containing 1."""
    for m in members:
        if isinstance(m, bool) != isinstance(value, bool):
            continue
        if m == value:
            return True
    return False


def _items_to_check(value, kind: TypeKind) -> List[Any]:
    """The individual values a set applies to.

    For a list-typed parameter the set constrains the **elements** -- a
    multi-valued selector like `views: [rtl, tlm]` is the whole point. A bare
    string in a list slot is an accepted alternate form (see `coerce_to_kind`),
    so it is split the same way the value itself will be.
    """
    if value is None:
        return []
    if kind is TypeKind.LIST:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            return [e for e in
                    (s.strip() for part in value.split(",") for s in part.split())
                    if e]
        return [value]
    # An empty string is how an unset scalar is spelled, and a value set must
    # not turn "not chosen" into an error.
    if value == "":
        return []
    return [value]


def format_value_error(name: str, bad: Any, valueset) -> str:
    """The diagnostic for a value outside the set, with a suggestion.

    Naming the alternatives is the entire benefit of declaring a value set, so
    the message always lists them and guesses at a near miss.
    """
    import difflib
    members, is_open = value_set_members(valueset)
    listing = ", ".join(str(m) for m in members)
    if is_open:
        # An open set does not forbid anything, so the wording says "unknown",
        # not "invalid" -- the value may well be right.
        msg = "%s'%s' is not a known value. Known values: %s, ..." % (
            ("%s: " % name) if name else "", bad, listing)
    else:
        msg = "%s'%s' is not a valid value. Valid values: %s" % (
            ("%s: " % name) if name else "", bad, listing)
    close = difflib.get_close_matches(
        str(bad), [str(m) for m in members], n=1, cutoff=0.6)
    if close:
        msg += ". Did you mean '%s'?" % close[0]
    return msg


def check_value_set(value, valueset, kind=TypeKind.ANY, *,
                    name: str = "", srcinfo: Any = None) -> Optional[str]:
    """Check `value` against a declared value set.

    Returns ``None`` when the value is acceptable, or a **warning message** when
    an *open* set does not list it -- an open set enumerates the known values
    without forbidding the rest, so the caller logs and carries on. A *closed*
    set raises :class:`ParamValueError` citing `srcinfo`.

    Never modifies the value: a value set accepts or rejects, it does not
    normalize. Callers run it after `coerce_to_kind`, so it always sees the
    final typed value.
    """
    members, is_open = value_set_members(valueset)
    if not members:
        return None

    kind = normalize_type(kind)
    if kind is TypeKind.MAP:
        raise ParamValueError(
            "%svalue sets are not supported for map-typed parameters" % (
                ("%s: " % name) if name else ""), srcinfo)

    for item in _items_to_check(value, kind):
        if not _member_of(item, members):
            msg = format_value_error(name, item, valueset)
            if is_open:
                return msg
            raise ParamValueError(msg, srcinfo)
    return None
