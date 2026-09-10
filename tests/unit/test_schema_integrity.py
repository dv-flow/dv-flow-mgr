"""The published schema must be resolvable.

`dv.flow.schema.json` is not only documentation input: it is what editors load
via ``# yaml-language-server: $schema=...``, and what any strict validator
checks a flow file against. A `$ref` pointing at a definition that is not in the
file makes the whole schema invalid -- the editor reports an error on the user's
flow file, and the cause is nowhere near where it shows up.

That is what happened. `CmdSchema.EXCLUDE_DEFS` drops internal types from the
user-facing schema, but `PackageDef.type` is annotated `List[PackageSpec]` and
still referenced it, so the shipped schema carried a dangling reference. It was
found by building the documentation, where `sphinx-jsonschema` reported it as
five "undefined label" warnings -- which read like a rendering glitch rather
than an invalid artifact.
"""
import json
import os
import re

import pytest

import dv_flow.mgr
from dv_flow.mgr.util.cmds.cmd_schema import CmdSchema


def _canonical():
    share = os.path.join(os.path.dirname(os.path.abspath(dv_flow.mgr.__file__)),
                         "share", "dv.flow.schema.json")
    with open(share) as fp:
        return json.load(fp)


def _refs(schema):
    return set(re.findall(r'#/defs/([A-Za-z_][A-Za-z0-9_]*)',
                          json.dumps(schema)))


def test_canonical_schema_has_no_dangling_refs():
    schema = _canonical()
    assert _refs(schema) - set(schema["defs"]) == set()


def test_generated_schema_has_no_dangling_refs():
    """Checked against a fresh generation as well as the checked-in file, so a
    model change that reintroduces the problem fails here rather than at the
    next person to regenerate."""
    schema = CmdSchema()._generate_schema()
    assert _refs(schema) - set(schema["defs"]) == set()


def test_the_checked_in_schema_is_current():
    """The canonical file is generated, so it can drift from the models.

    A stale schema is worse than no schema: it validates against yesterday's
    fields and rejects today's.
    """
    generated = CmdSchema()._generate_schema()
    assert generated == _canonical(), (
        "dv.flow.schema.json is out of date -- regenerate with "
        "`dfm util schema --generate -o src/dv_flow/mgr/share/dv.flow.schema.json`")


def test_unreferenced_internals_are_still_excluded():
    """The repair must not amount to giving up on filtering."""
    defs = set(CmdSchema()._generate_schema()["defs"])
    assert 'SrcInfo' not in defs
    assert 'TaskBodyDef' not in defs


def test_a_referenced_internal_is_kept():
    """`PackageSpec` stays only because `PackageDef.type` still points at it.

    If this ever fails, the annotation was fixed and the definition can go --
    which is the better outcome, and this test is where to notice it.
    """
    defs = set(CmdSchema()._generate_schema()["defs"])
    assert 'PackageSpec' in defs
