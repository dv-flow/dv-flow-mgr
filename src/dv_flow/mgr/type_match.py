#****************************************************************************
#* type_match.py
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
"""Matching a produced data item against a wanted pattern.

One implementation, shared by `dfm validate`'s dataflow check and by
`std.check.Needs`, so the two cannot disagree about whether a producer
satisfies a consumer.

Two rules, and the second is the one that is easy to get wrong:

* **Subset match on attributes.** Every attribute the pattern names must be
  present on the item with the same value; the item may carry more. That is
  what lets `{type: SimImg}` accept a profiling image while
  `{type: SimImg, profile: true}` does not accept a plain one.
* **`type:` matches by IS-A, not by string equality.** `std.PubSet` derives from
  `std.FileSet`, so a consumer asking for a FileSet must accept a PubSet.
  Exact-string matching silently rejects it -- and the rejection looks like a
  miswired flow rather than a matching bug, which is the worst way to be wrong.
"""

import logging

_log = logging.getLogger("type_match")


def is_a(item_type, wanted_type, resolve=None) -> bool:
    """True when `item_type` is `wanted_type` or derives from it.

    `resolve(name) -> Type | None` looks a type up; without it this degrades to
    string equality, which is the honest answer when no type registry is
    available (a consumer with no loader should not start rejecting things it
    cannot reason about).
    """
    if item_type == wanted_type:
        return True
    if resolve is None:
        return False

    typ = None
    try:
        typ = resolve(item_type)
    except Exception:
        return False

    seen = set()
    while typ is not None and id(typ) not in seen:
        seen.add(id(typ))
        if getattr(typ, 'name', None) == wanted_type:
            return True
        typ = getattr(typ, 'uses', None)
    return False


def values_equal(a, b) -> bool:
    """Compare two attribute values.

    Booleans are compared leniently because a value that arrives through a
    `${{ }}` expression is the string 'true' while one written literally in
    YAML is a bool -- a match failing on that distinction would be
    indefensible to the person who wrote both.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return _as_bool(a) == _as_bool(b)
    return str(a) == str(b)


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def pattern_matches(wanted, item, resolve=None) -> bool:
    """True when the produced `item` pattern satisfies the `wanted` pattern."""
    for key, value in wanted.items():
        if key == "type":
            if not is_a(item.get("type"), value, resolve):
                return False
            continue
        if key not in item:
            return False
        if not values_equal(item[key], value):
            return False
    return True


def normalize(value):
    """Normalize a pattern written as a bare string to a map.

    `produces: std.FileSet` is shorthand for `{type: std.FileSet}` -- the common
    case is "an item of this type", and making that spell out a map is noise.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return {"type": value} if value else None
    if isinstance(value, dict):
        cleaned = {k: v for k, v in value.items() if v is not None}
        return cleaned or None
    return None
