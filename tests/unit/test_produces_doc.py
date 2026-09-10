"""`doc:` on a `produces:` entry.

A task declares what it produces by KIND -- the item type -- which is the
minimum a consumer needs in order to wire up. It is not what a *person* needs:
"an std.FileSet" does not tell anyone that the file lands at
`${{ task_rundir }}/ral_pkg.sv`.

`doc:` carries that. It is deliberately the smallest thing that could work: no
schema for paths, no globs, no declared file lists. Prose, next to the type it
describes.

Two properties make it prose rather than data, and both are load-bearing:

1. **It is not an attribute.** Every other key in a `produces:` entry is
   something a consumer can match on. If `doc:` were one, a producer's wording
   would be part of the wiring, and editing a sentence could change which tasks
   connect.
2. **It is not evaluated.** `${{ task_rundir }}` has no value outside a run, and
   even where it resolves, the result is one machine's path. The unresolved form
   is what generalises, so it is what reaches the reader.
"""
import os

import pytest

from dv_flow.mgr import PackageLoader
from dv_flow.mgr.produces_eval import ProducesEvaluator
from dv_flow.mgr.type_match import NON_ATTRIBUTE_KEYS, pattern_matches
from .marker_collector import MarkerCollector


def _load(tmpdir, flow, name="flow.dv"):
    with open(os.path.join(str(tmpdir), name), "w") as f:
        f.write(flow)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), name))
    assert [m.msg for m in collector.markers] == []
    return pkg


FLOW = """\
package:
    name: p
    imports:
    - std
    tasks:
    - name: Gen
      produces:
      - type: std.FileSet
        filetype: verilogSource
        doc: ${{ task_rundir }}/ral_pkg.sv
    - name: Use
      consumes:
      - type: std.FileSet
        filetype: verilogSource
"""


# ----------------------------------------------------------------- loading

def test_doc_survives_loading(tmpdir):
    pkg = _load(tmpdir, FLOW)
    produces = pkg.task_m["p.Gen"].produces
    assert produces[0]["doc"] == "${{ task_rundir }}/ral_pkg.sv"


def test_doc_does_not_displace_the_attributes(tmpdir):
    pkg = _load(tmpdir, FLOW)
    entry = pkg.task_m["p.Gen"].produces[0]
    assert entry["type"] == "std.FileSet"
    assert entry["filetype"] == "verilogSource"


# -------------------------------------------------------------- evaluation

def test_doc_is_not_evaluated():
    """`${{ task_rundir }}` reaches the reader intact.

    Evaluating it would bake whichever machine built the docs into the page --
    and outside a run there is nothing for it to resolve to anyway.
    """
    evaluated = ProducesEvaluator().evaluate(
        [{"type": "std.FileSet", "doc": "${{ task_rundir }}/ral_pkg.sv"}],
        params=None)
    assert evaluated[0]["doc"] == "${{ task_rundir }}/ral_pkg.sv"


def test_other_keys_are_still_evaluated():
    """The exclusion is for `doc:` alone; attributes keep working."""
    class Params:
        type = "verilogSource"

    evaluated = ProducesEvaluator().evaluate(
        [{"type": "std.FileSet", "filetype": "${{ params.type }}"}],
        params=Params())
    assert evaluated[0]["filetype"] == "verilogSource"


def test_evaluation_does_not_warn_about_doc(tmpdir, caplog):
    """An unresolvable reference in `doc:` must be silent, not a warning.

    It is not a failed evaluation -- it was never an evaluation. Warning here
    would put a line in the log for every documented output.
    """
    import logging
    with caplog.at_level(logging.WARNING):
        ProducesEvaluator().evaluate(
            [{"type": "std.FileSet", "doc": "${{ nothing_defined }}/x.sv"}],
            params=None)
    assert "Failed to evaluate" not in caplog.text


# ---------------------------------------------------------------- matching

def test_doc_is_declared_a_non_attribute():
    assert "doc" in NON_ATTRIBUTE_KEYS


def test_doc_does_not_affect_matching():
    """Two producers whose prose differs satisfy the same consumer.

    If `doc:` were an attribute, editing a sentence would change which tasks
    connect to which.
    """
    wanted = {"type": "std.FileSet", "filetype": "verilogSource"}
    a = {"type": "std.FileSet", "filetype": "verilogSource", "doc": "a.sv"}
    b = {"type": "std.FileSet", "filetype": "verilogSource", "doc": "b.sv"}
    assert pattern_matches(wanted, a)
    assert pattern_matches(wanted, b)


def test_a_consumer_cannot_require_a_doc_string():
    """`doc:` on the WANTED side is ignored rather than treated as a filter.

    Nobody should write this, but if they do, the sensible reading is that they
    documented their input -- not that they want only producers whose prose
    matches character for character.
    """
    wanted = {"type": "std.FileSet", "doc": "whatever I wrote here"}
    item = {"type": "std.FileSet"}
    assert pattern_matches(wanted, item)


def test_dataflow_still_wires_up_end_to_end(tmpdir):
    """The whole point: adding documentation must not change the graph."""
    from dv_flow.mgr.dataflow_matcher import DataflowMatcher
    pkg = _load(tmpdir, FLOW)
    gen = pkg.task_m["p.Gen"]
    use = pkg.task_m["p.Use"]
    matcher = DataflowMatcher()
    assert matcher.check_compatibility(
        use.consumes, gen.produces, "p.Use", "p.Gen") is not False
