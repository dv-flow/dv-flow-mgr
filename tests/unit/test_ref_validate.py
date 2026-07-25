"""Phase A of run_body_expansion_plan.md: reference validation as its own pass.

Two concerns, deliberately kept apart:
  - expr_refs -- what names does an expression reference? (no values)
  - ref_validate -- are those names bound? (scope signature, no values)
"""
import os

import pytest

from dv_flow.mgr import PackageLoader
from dv_flow.mgr.expr_refs import refs_of_expr, refs_of_text, has_refs
from dv_flow.mgr.ref_validate import (
    LOAD_NAMES, OPAQUE_NAMES, RUN_NAMES, ScopeSignature, signature_for_task,
    validate_task_refs)

from .marker_collector import MarkerCollector


def _load(tmpdir, flow_dv, **kwargs):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[collector], **kwargs)
    pkg = loader.load(os.path.join(str(tmpdir), "flow.dv"))
    return pkg, collector


def _errors(collector):
    return [m.msg for m in collector.markers
            if str(getattr(m, "severity", "")).lower().endswith("error")]


# ---------------------------------------------------------------- expr_refs

def test_bare_reference():
    assert [r.root for r in refs_of_text("a=${{ a }}")] == ["a"]


def test_hierarchical_reference_reports_its_root():
    (ref,) = refs_of_text("${{ env.CC }}")
    assert ref.root == "env"
    assert ref.path == "env.CC"


def test_multiple_references_in_one_string():
    assert [r.root for r in refs_of_text("${{ a }}/${{ b }}")] == ["a", "b"]


def test_default_syntax_is_marked():
    (ref,) = refs_of_text("${{ CC:-gcc }}")
    assert ref.root == "CC"
    assert ref.has_default


def test_a_filter_name_is_not_a_reference():
    """`files | length` references `files`; `length` is a builtin. Reporting
    it as an undefined variable is the false positive this guards."""
    assert [r.root for r in refs_of_text("${{ files | length }}")] == ["files"]


def test_a_method_name_is_not_a_reference():
    assert [r.root for r in refs_of_text("${{ shell('echo hi') }}")] == []


def test_map_and_select_bind_their_element_names():
    """map()/select() bind `input`/`item` per element, so a reference to
    either inside the argument is bound, not dangling."""
    roots = [r.root for r in refs_of_text("${{ xs | select(input.a == b) }}")]
    assert roots == ["xs", "b"]


def test_index_expressions_are_walked():
    assert [r.root for r in refs_of_text("${{ a[b] }}")] == ["a", "b"]


def test_non_strings_and_plain_strings_yield_nothing():
    assert refs_of_text(None) == []
    assert refs_of_text(42) == []
    assert refs_of_text(["${{ a }}"]) == []   # lists are the caller's job
    assert refs_of_text("no references here") == []


def test_has_refs():
    assert has_refs("x ${{ a }}")
    assert not has_refs("x")
    assert not has_refs(None)


def test_unparseable_expression_yields_no_refs():
    """A syntax error is a different diagnostic; this pass must not turn it
    into a bogus undefined-variable report."""
    assert refs_of_expr("!!!") == []


# ----------------------------------------------------------- ScopeSignature

def test_reserved_names_are_bound():
    sig = ScopeSignature()
    for name in list(LOAD_NAMES) + list(RUN_NAMES) + list(OPAQUE_NAMES):
        assert sig.is_bound(name), name


def test_available_excludes_the_reserved_vocabulary():
    """A suggestion should offer the task's own scope, not `result_file`."""
    sig = ScopeSignature(params={"seed"}, package_vars={"base"})
    assert sig.available() == ["base", "seed"]


def test_signature_includes_inherited_params(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: base
      with:
        seed: { type: int, value: 0 }
      run: echo base
    - name: derived
      uses: base
      with:
        extra: { type: str, value: "x" }
      run: echo derived
"""
    pkg, _ = _load(tmpdir, flow_dv)
    sig = signature_for_task(pkg.task_m["p.derived"])
    assert "seed" in sig.params
    assert "extra" in sig.params


def test_signature_includes_package_vars(tmpdir):
    flow_dv = """\
package:
    name: p
    with:
      base: { type: str, value: "B" }
    tasks:
    - name: t
      run: echo hi
"""
    pkg, _ = _load(tmpdir, flow_dv)
    assert "base" in signature_for_task(pkg.task_m["p.t"]).package_vars


# ------------------------------------------------------- load-time findings

def test_dangling_ref_in_run_is_an_error(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      run: echo "${{ seedd }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    msgs = _errors(collector)
    assert any("undefined variable 'seedd'" in m for m in msgs), msgs


def test_dangling_ref_in_a_param_default_is_an_error(tmpdir):
    """The case eager expansion used to catch for free and deferred
    evaluation no longer does."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        a: { type: str, value: "${{ nosuch }}" }
      run: echo hi
"""
    _, collector = _load(tmpdir, flow_dv)
    msgs = _errors(collector)
    assert any("undefined variable 'nosuch'" in m for m in msgs), msgs
    assert any("parameter 'a'" in m for m in msgs), msgs


def test_finding_is_located(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      run: echo "${{ seedd }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    marker = next(m for m in collector.markers if "seedd" in m.msg)
    assert marker.loc is not None
    assert marker.loc.path.endswith("flow.dv")


def test_message_names_the_task_and_a_suggestion(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        seed: { type: int, value: 1 }
      run: echo "${{ sed }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    msg = next(m for m in _errors(collector) if "undefined variable" in m)
    assert "p.t" in msg
    assert "Did you mean 'seed'?" in msg


def test_message_lists_available_names_when_nothing_is_close(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        seed: { type: int, value: 1 }
      run: echo "${{ zzzzz }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    msg = next(m for m in _errors(collector) if "undefined variable" in m)
    assert "Available: seed" in msg


# ------------------------------------------------------ accepted references

@pytest.mark.parametrize("expr,extra", [
    ("${{ srcdir }}", ""),                     # load phase
    ("${{ rundir }}", ""),                     # run phase
    ("${{ env.HOME }}", ""),                   # load phase, hierarchical
    ("${{ NOPE:-fallback }}", ""),             # supplies its own default
    ("${{ this.seed }}", ""),                  # opaque root
    ("${{ matrix.sim }}", ""),                 # opaque root
    ("${{ seed }}", "seed: { type: int, value: 1 }"),   # own param
])
def test_valid_references_produce_no_error(tmpdir, expr, extra):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        %s
      run: echo "%s"
""" % (extra if extra else "unused: { type: str, value: \"\" }", expr)
    _, collector = _load(tmpdir, flow_dv)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_inherited_param_reference_is_valid(tmpdir):
    """An inherited parameter is as referenceable as a local one."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: base
      with:
        seed: { type: int, value: 0 }
      run: echo base
    - name: derived
      uses: base
      run: echo "${{ seed }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_package_var_reference_is_valid(tmpdir):
    flow_dv = """\
package:
    name: p
    with:
      base: { type: str, value: "B" }
    tasks:
    - name: t
      run: echo "${{ base }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_package_qualified_reference_is_valid(tmpdir):
    flow_dv = """\
package:
    name: p
    with:
      base: { type: str, value: "B" }
    tasks:
    - name: t
      run: echo "${{ p.base }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_compound_subtask_may_reference_parent_params(tmpdir):
    """A compound body binds the parent's params as bare names."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: outer
      with:
        seed: { type: int, value: 7 }
      body:
      - name: inner
        run: echo "${{ seed }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_compound_subtask_typo_is_still_caught(tmpdir):
    flow_dv = """\
package:
    name: p
    tasks:
    - name: outer
      with:
        seed: { type: int, value: 7 }
      body:
      - name: inner
        run: echo "${{ seeed }}"
"""
    _, collector = _load(tmpdir, flow_dv)
    assert any("undefined variable 'seeed'" in m for m in _errors(collector)), \
        _errors(collector)


# ------------------------------------------------------------- the two seams

def test_validation_can_be_switched_off_in_one_place(tmpdir):
    """The relaxation path: description validation becomes opt-in by
    flipping this flag, not by unpicking checks from the loader."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        a: { type: str, value: "${{ nosuch }}" }
      run: echo hi
"""
    _, collector = _load(tmpdir, flow_dv, validate_refs=False)
    assert not [m for m in _errors(collector) if "undefined variable" in m], \
        _errors(collector)


def test_validate_task_refs_needs_no_loader_state(tmpdir):
    """Callable standalone on a loaded package -- this is what makes the
    `dfm validate` call site independent of the load-time one."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        a: { type: str, value: "${{ nosuch }}" }
      run: echo hi
"""
    pkg, _ = _load(tmpdir, flow_dv, validate_refs=False)
    findings = validate_task_refs(pkg.task_m["p.t"])
    assert [f.ref.root for f in findings] == ["nosuch"]
    assert findings[0].where == "parameter 'a'"


def test_run_text_override(tmpdir):
    """The load-time caller validates before the body is stored, so it
    supplies the text; every other caller gets task.run."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      run: echo hi
"""
    pkg, _ = _load(tmpdir, flow_dv)
    task = pkg.task_m["p.t"]
    assert validate_task_refs(task) == []
    findings = validate_task_refs(task, run_text="echo ${{ bogus }}")
    assert [f.ref.root for f in findings] == ["bogus"]
    assert findings[0].where == "run"


def test_nested_param_value_is_walked(tmpdir):
    """A reference inside a list- or map-valued parameter is reported with
    the path to it, not just the parameter name."""
    flow_dv = """\
package:
    name: p
    tasks:
    - name: t
      with:
        opts: { type: list, value: ["-a", "${{ nosuch }}"] }
      run: echo hi
"""
    pkg, _ = _load(tmpdir, flow_dv, validate_refs=False)
    findings = validate_task_refs(pkg.task_m["p.t"])
    assert len(findings) == 1
    assert findings[0].where == "parameter 'opts[1]'"
