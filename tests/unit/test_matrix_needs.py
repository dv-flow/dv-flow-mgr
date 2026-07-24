"""Matrix-driven `needs:` — a matrix body cell may reference a matrix variable
in its `needs:` (e.g. `needs: ["${{ this.image }}"]`), resolved per cell (mirrors
the existing matrix-driven `uses:`). Enables a 2D image x case suite where each
cell depends on its image."""
import os
from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


def _build(flow_text, tmp_path):
    (tmp_path / "flow.dv").write_text(flow_text)
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    return TaskGraphBuilder(root_pkg=pkg,
                            rundir=str(tmp_path / "rundir"), loader=loader)


def _cells(node):
    out = []
    def walk(n):
        for t in getattr(n, "tasks", []) or []:
            if t is n:
                continue
            out.append(t)
            walk(t)
    walk(node)
    return out


def test_needs_references_matrix_var(tmp_path):
    b = _build("""\
package:
  name: q
  tasks:
  - name: imgA
    uses: std.Message
    with: {msg: A}
  - name: imgB
    uses: std.Message
    with: {msg: B}
  - name: reg
    strategy:
      matrix:
        image: [ imgA, imgB ]
        case:
        - { testname: t1 }
        - { testname: t2 }
    body:
    - name: "${{ this.image }}-${{ this.case.testname }}"
      uses: std.Message
      needs: [ "${{ this.image }}" ]
      with: { msg: x }
""", tmp_path)
    n = b.mkTaskNode("q.reg")
    cells = [c for c in _cells(n)
             if c.name.count("-") and "img" in c.name.lower()
             and c.name.rsplit(".", 1)[-1].startswith("img")]
    # 2 images x 2 cases = 4 cells
    assert len(cells) == 4
    need_of = {}
    for c in cells:
        img_needs = [nd.name for nd, _ in c.needs if nd.name.rsplit(".", 1)[-1] in ("imgA", "imgB")]
        assert len(img_needs) == 1, "cell %s should need exactly its image, got %s" % (
            c.name, [nd.name for nd, _ in c.needs])
        need_of[c.name.rsplit(".", 1)[-1]] = img_needs[0].rsplit(".", 1)[-1]
    # each cell needs the image named by its own `this.image`
    for leaf, img in need_of.items():
        assert leaf.startswith(img), "%s wired to %s" % (leaf, img)


def test_matrix_need_resolving_to_unknown_task_errors(tmp_path):
    # A deferred matrix need that resolves (per cell) to a name that is not a
    # known task must fail loudly -- the deferral must not swallow real errors.
    import pytest
    b = _build("""\
package:
  name: q
  tasks:
  - name: reg
    strategy:
      matrix:
        image: [ does_not_exist ]
    body:
    - name: "c_${{ this.image }}"
      uses: std.Message
      needs: [ "${{ this.image }}" ]
      with: { msg: x }
""", tmp_path)
    with pytest.raises(Exception, match="does_not_exist|not a known task"):
        b.mkTaskNode("q.reg")


def _images_used(builder, task):
    n = builder.mkTaskNode(task)
    imgs = set()
    def walk(x):
        for nd, _ in getattr(x, "needs", []):
            leaf = nd.name.rsplit(".", 1)[-1]
            if leaf in ("imgA", "imgB", "imgC"):
                imgs.add(leaf)
        for t in getattr(x, "tasks", []) or []:
            if t is not x:
                walk(t)
    walk(n)
    return sorted(imgs)


_AXIS_FLOW = """\
package:
  name: q
  with:
    images: { type: list, value: [imgA, imgB, imgC] }
  tasks:
  - name: imgA
    uses: std.Message
    with: {msg: A}
  - name: imgB
    uses: std.Message
    with: {msg: B}
  - name: imgC
    uses: std.Message
    with: {msg: C}
  - name: reg
    strategy:
      matrix:
        image: "${{ images }}"
        case: [ {t: t1}, {t: t2} ]
    body:
    - name: "${{ this.image }}-${{ this.case.t }}"
      uses: std.Message
      needs: [ "${{ this.image }}" ]
      with: {msg: x}
"""


def _build_axis(tmp_path, overrides=None):
    from dv_flow.mgr import PackageLoader
    (tmp_path / "flow.dv").write_text(_AXIS_FLOW)
    loader = PackageLoader(param_overrides=overrides or {})
    pkg = loader.load(str(tmp_path / "flow.dv"))
    return TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "rundir"), loader=loader)


def test_matrix_axis_from_variable_default(tmp_path):
    b = _build_axis(tmp_path)
    assert _images_used(b, "q.reg") == ["imgA", "imgB", "imgC"]


def test_matrix_axis_cli_single(tmp_path):
    b = _build_axis(tmp_path, {"images": "imgA"})
    assert _images_used(b, "q.reg") == ["imgA"]


def test_matrix_axis_cli_comma_subset(tmp_path):
    b = _build_axis(tmp_path, {"images": "imgA,imgC"})
    assert _images_used(b, "q.reg") == ["imgA", "imgC"]


def test_contains_builtin():
    from dv_flow.mgr.expr_eval import ExprEval
    ee = ExprEval()
    ee.set("xs", ["tlm", "rtl"])
    assert ee.eval_obj("xs | contains(\"tlm\")") is True
    assert ee.eval_obj("xs | contains(\"wb\")") is False


def test_needs_alias_via_map_index(tmp_path):
    # `needs: ["${{ image_of[this.image] }}"]` maps a short alias to the real
    # image task, per cell.
    from dv_flow.mgr import PackageLoader
    (tmp_path / "flow.dv").write_text("""\
package:
  name: q
  with:
    images: { type: list, value: [tlm, rtl] }
    image_of: { type: map, value: { tlm: imgA, rtl: imgB } }
  tasks:
  - name: imgA
    uses: std.Message
    with: {msg: A}
  - name: imgB
    uses: std.Message
    with: {msg: B}
  - name: reg
    strategy:
      matrix:
        image: "${{ images }}"
    body:
    - name: "${{ this.image }}"
      uses: std.Message
      needs: [ "${{ image_of[this.image] }}" ]
      with: {msg: x}
""")
    loader = PackageLoader()
    pkg = loader.load(str(tmp_path / "flow.dv"))
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "rundir"), loader=loader)
    assert _images_used(b, "q.reg") == ["imgA", "imgB"]
