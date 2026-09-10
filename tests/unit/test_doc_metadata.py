"""Metadata that exists so tools can document a flow.

None of it changes what a task does. It is here because the alternative --
having a documentation generator re-parse the YAML and guess -- puts a second,
silently-diverging model of the flow in the world.
"""
import os

import pytest

from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def _load(tmpdir, flow_dv, name="flow.dv"):
    with open(os.path.join(str(tmpdir), name), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), name))
    assert [m.msg for m in collector.markers] == []
    return pkg


# --------------------------------------------------------------- package doc

def test_package_doc_is_loaded(tmpdir):
    """`desc` is the listing line; `doc` is the page."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    desc: One line about pkg
    doc: |
      The longer story: what this package is for, and which task to run first.
    tasks:
    - name: T
""")
    assert pkg.desc == "One line about pkg"
    assert pkg.doc.startswith("The longer story:")


def test_package_doc_defaults_to_none(tmpdir):
    """Absent prose is absent, not empty-string prose."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: T
""")
    assert pkg.doc is None


def test_package_doc_survives_lazy_materialization(tmpdir):
    """`doc` must be in _LAZY_ATTRS.

    A lazy package answers attribute reads by materializing first. A data
    field missing from that set reads its class default instead -- so `doc`
    would come back None on exactly the imported packages a docs build cares
    about, with nothing to indicate the value was never looked up.
    """
    from dv_flow.mgr.package import Package
    lazy = [c for c in Package.__subclasses__()
            if hasattr(c, "_LAZY_ATTRS")]
    assert lazy, "expected a lazy Package subclass declaring _LAZY_ATTRS"
    for cls in lazy:
        assert "doc" in cls._LAZY_ATTRS
        assert "desc" in cls._LAZY_ATTRS


# ------------------------------------------------------------------ examples

def test_task_examples_are_loaded(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: T
      desc: Does a thing
      examples:
      - title: Run it
        caption: The usual invocation.
        lang: shell
        code: dfm run T
      - code: |
          - name: mine
            uses: pkg.T
""")
    examples = pkg.task_m["pkg.T"].examples
    assert len(examples) == 2

    assert examples[0].title == "Run it"
    assert examples[0].caption == "The usual invocation."
    assert examples[0].lang == "shell"
    assert examples[0].code == "dfm run T"

    # Everything but `code` is optional; `lang` falls back to yaml because a
    # flow-file fragment is the common case.
    assert examples[1].title is None
    assert examples[1].caption is None
    assert examples[1].lang == "yaml"
    assert "uses: pkg.T" in examples[1].code


def test_task_examples_default_empty(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: T
""")
    assert pkg.task_m["pkg.T"].examples == []


def test_example_requires_code(tmpdir):
    """An example with no code is a heading, and a heading is not an example."""
    with pytest.raises(Exception):
        _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: T
      examples:
      - title: Just a title
""")


def test_examples_are_not_inherited(tmpdir):
    """An example names a task and its parameters.

    Showing a base task's example under a derived task would show the reader
    something they cannot type -- so `uses:` does not carry examples down,
    even though it carries `desc`.
    """
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      desc: base description
      examples:
      - code: dfm run Base
        lang: shell
    - name: Derived
      uses: Base
""")
    assert len(pkg.task_m["pkg.Base"].examples) == 1
    assert pkg.task_m["pkg.Derived"].examples == []


def test_subtask_examples_are_loaded(tmpdir):
    """Compound bodies go through a separate construction path."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Outer
      body:
      - name: Inner
        examples:
        - code: "inner example"
          lang: shell
""")
    outer = pkg.task_m["pkg.Outer"]
    inner = [t for t in outer.subtasks if t.name.endswith("Inner")]
    assert len(inner) == 1
    assert [e.code for e in inner[0].examples] == ["inner example"]


# ---------------------------------------------------------- lifecycle tagging

@pytest.mark.parametrize("tag", ["std.Stable", "std.Experimental",
                                 "std.Deprecated"])
def test_lifecycle_tag_types_exist(tmpdir, tag):
    """Lifecycle is a claim about an interface, so it lives in the type system
    rather than in a doc-comment convention no tool can check."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    imports:
    - std
    tasks:
    - name: T
      tags:
      - %s
""" % tag)
    assert pkg.task_m["pkg.T"] is not None


def test_deprecated_carries_replacement(tmpdir):
    """The point of the tag is the pointer to what to use instead."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    imports:
    - std
    tasks:
    - name: Old
      tags:
      - std.Deprecated:
          reason: superseded by the streaming implementation
          replacement: pkg.New
          since: "1.4"
    - name: New
""")
    tags = pkg.task_m["pkg.Old"].tags
    assert len(tags) == 1
    params = tags[0].paramT
    assert params.replacement == "pkg.New"
    assert params.since == "1.4"
    assert "streaming" in params.reason


def test_experimental_reason_defaults_empty(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    imports:
    - std
    tasks:
    - name: T
      tags:
      - std.Experimental
""")
    params = pkg.task_m["pkg.T"].tags[0].paramT
    assert params.reason == ""


# ------------------------------------------------- desc/doc inherit via uses

def test_prose_is_inherited_through_uses(tmpdir):
    """A task that only narrows its base is still described by that base."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      desc: The one-liner
      doc: The long form
    - name: Derived
      uses: Base
""")
    t = pkg.task_m["pkg.Derived"]
    assert t.desc == "The one-liner"
    assert t.doc == "The long form"


def test_own_prose_wins_over_inherited(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      desc: Base line
      doc: Base page
    - name: Derived
      uses: Base
      desc: Derived line
      doc: Derived page
""")
    t = pkg.task_m["pkg.Derived"]
    assert t.desc == "Derived line"
    assert t.doc == "Derived page"


def test_desc_and_doc_inherit_independently(tmpdir):
    """Restating the summary while leaning on the base for the long form.

    The fields answer different questions, so a task may reasonably author one
    and not the other.
    """
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      desc: Base line
      doc: Base page
    - name: Derived
      uses: Base
      desc: Derived line
""")
    t = pkg.task_m["pkg.Derived"]
    assert t.desc == "Derived line"
    assert t.doc == "Base page"


def test_prose_inherits_across_a_chain(tmpdir):
    """Two links up, with the middle link contributing nothing."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: A
      desc: From A
    - name: B
      uses: A
    - name: C
      uses: B
""")
    assert pkg.task_m["pkg.C"].desc == "From A"


def test_prose_inherits_regardless_of_declaration_order(tmpdir):
    """The base is declared after the task that uses it.

    Tasks elaborate in declaration order, so reading one level deep would give
    a different answer here than in the ordered case -- and file order is not
    something an author should have to think about to get a description.
    """
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: C
      uses: B
    - name: B
      uses: A
    - name: A
      desc: From A
""")
    assert pkg.task_m["pkg.C"].desc == "From A"


def test_prose_inherits_into_compound_body_tasks(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
      desc: From Base
    - name: Outer
      body:
      - name: inner
        uses: Base
""")
    inner = [st for st in pkg.task_m["pkg.Outer"].subtasks
             if st.name.endswith("inner")]
    assert len(inner) == 1
    assert inner[0].desc == "From Base"


def test_no_base_prose_leaves_empty(tmpdir):
    """Absence stays absence -- inheritance fills gaps, it does not invent."""
    pkg = _load(tmpdir, """\
package:
    name: pkg
    tasks:
    - name: Base
    - name: Derived
      uses: Base
""")
    assert pkg.task_m["pkg.Derived"].desc == ""
    assert pkg.task_m["pkg.Derived"].doc == ""
