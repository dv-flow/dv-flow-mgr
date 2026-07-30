#****************************************************************************
#* test_strategy_select.py
#*
#* `strategy.select`: a family of independently-addressable artifact variants.
#*
#* The contract being pinned:
#*   * a cell is a REAL TASK in the package namespace -- `needs: [f.cell]`, the
#*     CLI, and `show` all reach it with no per-consumer special-casing;
#*   * an unaddressed cell is NEVER BUILT. This is the difference from `matrix:`,
#*     where running the task runs every cell;
#*   * two consumers of one cell get ONE build. Only possible because a cell has
#*     a stable name to memoize on, which a matrix cell does not;
#*   * a family's SHAPE is fixed at load. Axes may not depend on a `set:`/`let`
#*     rebind, or the same cell name would mean different things by site.
#****************************************************************************
import asyncio
import os
import textwrap

import pytest

from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.util import loadProjPkgDef


def _write(tmpdir, flow):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(textwrap.dedent(flow))
    return str(tmpdir)


def _load(tmpdir, flow):
    return loadProjPkgDef(_write(tmpdir, flow))


def _errors(tmpdir, flow):
    msgs = []
    loadProjPkgDef(_write(tmpdir, flow),
                   listener=lambda m: msgs.append(m.msg))
    return msgs


def _builder(tmpdir, loader, pkg, **kw):
    return TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"),
        loader=loader, **kw)


def _run(tmpdir, node):
    runner = TaskSetRunner(rundir=os.path.join(str(tmpdir), "rundir"))
    return asyncio.run(runner.run(node))


BASIC = '''\
package:
    name: p
    tasks:
    - name: img
      strategy:
        select:
          axes:
            view: [tlm, rtl]
            build: [opt, prof]
        body:
        - uses: std.Message
          with:
            msg: "view=${{ this.view }} build=${{ this.build }}"
'''


# ---------------------------------------------------------------------------
# Declaration: cells are tasks
# ---------------------------------------------------------------------------

def test_cells_are_registered_as_tasks(tmpdir):
    _, pkg = _load(tmpdir, BASIC)
    assert sorted(k for k in pkg.task_m if k.startswith("p.img")) == [
        "p.img", "p.img.rtl.opt", "p.img.rtl.prof",
        "p.img.tlm.opt", "p.img.tlm.prof"]


def test_default_key_is_axis_values_in_declaration_order(tmpdir):
    _, pkg = _load(tmpdir, BASIC)
    assert pkg.task_m["p.img.rtl.opt"].select_bindings == {
        "view": "rtl", "build": "opt"}


def test_key_template_overrides_the_default_name(tmpdir):
    _, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                view: [tlm, rtl]
                build: [opt, prof]
              key: "${{ this.build }}-${{ this.view }}"
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    assert "p.img.prof-rtl" in pkg.task_m
    assert "p.img.rtl.prof" not in pkg.task_m


def test_cells_inherit_the_family_scope(tmpdir):
    """A `root:` family yields runnable cells -- that is what makes
    `dfm run sim-img.prof` work."""
    _, pkg = _load(tmpdir, BASIC.replace("- name: img", "- root: img"))
    assert pkg.task_m["p.img.tlm.opt"].is_root is True


def test_cells_inherit_params_from_the_body(tmpdir):
    """A cell's interior is the family's body task, so `collect_task_params`,
    tags, and produces all see what the built node will."""
    from dv_flow.mgr.task import collect_task_params
    _, pkg = _load(tmpdir, BASIC)
    definitions, _ = collect_task_params(pkg.task_m["p.img.tlm.opt"])
    assert "msg" in definitions


def test_axis_from_a_package_variable(tmpdir):
    _, pkg = _load(tmpdir, '''\
    package:
        name: p
        with:
          builds: {type: list, value: [opt, prof]}
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: "${{ builds }}"
            body:
            - uses: std.Message
              with: {msg: "${{ this.build }}"}
    ''')
    assert sorted(k for k in pkg.task_m if k.startswith("p.img.")) == [
        "p.img.opt", "p.img.prof"]


def test_a_define_on_the_axis_variable_changes_the_cell_set(tmpdir):
    flow = '''\
    package:
        name: p
        with:
          builds: {type: list, value: [opt, prof, cov]}
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: "${{ builds }}"
            body:
            - uses: std.Message
              with: {msg: "${{ this.build }}"}
    '''
    d = _write(tmpdir, flow)
    _, pkg = loadProjPkgDef(d, parameter_overrides={'package': {'builds': 'opt,cov'}})
    assert sorted(k for k in pkg.task_m if k.startswith("p.img.")) == [
        "p.img.cov", "p.img.opt"]


# ---------------------------------------------------------------------------
# Reference: cells are ordinary need targets
# ---------------------------------------------------------------------------

NEEDS = '''\
package:
    name: p
    tasks:
    - name: img
      strategy:
        select:
          axes:
            build: [opt, prof]
        body:
        - uses: std.Message
          with: {msg: "img ${{ this.build }}"}
    - name: consumer-a
      uses: std.Message
      needs: [img.prof]
      with: {msg: a}
    - name: consumer-b
      uses: std.Message
      needs: [img.prof]
      with: {msg: b}
    - root: both
      uses: std.Message
      needs: [consumer-a, consumer-b]
      with: {msg: both}
'''


def test_a_cell_can_be_a_need(tmpdir):
    loader, pkg = _load(tmpdir, NEEDS)
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.consumer-a")
    assert [n.name for n, _ in node.needs] == ["p.img.prof"]


def test_a_cell_declared_after_its_consumer_still_resolves(tmpdir):
    """Cells are declared in the same pass as ordinary tasks, so a reference
    does not depend on which is written first."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: consumer
          uses: std.Message
          needs: [img.prof]
          with: {msg: c}
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - uses: std.Message
              with: {msg: "img"}
    ''')
    b = _builder(tmpdir, loader, pkg)
    assert [n.name for n, _ in b.mkTaskNode("p.consumer").needs] == ["p.img.prof"]


def test_two_consumers_of_one_cell_share_a_single_node(tmpdir):
    """The build-once property. Only reachable because a cell has a stable
    name for the node memo to key on."""
    loader, pkg = _load(tmpdir, NEEDS)
    b = _builder(tmpdir, loader, pkg)
    b.mkTaskNode("p.both")
    a_need = b._task_node_m["p.consumer-a"].needs[0][0]
    b_need = b._task_node_m["p.consumer-b"].needs[0][0]
    assert a_need is b_need


def test_an_unaddressed_cell_is_never_built(tmpdir):
    """The point of the whole feature: asking for one artifact must not build
    its siblings. `iff:` cannot deliver this -- it still constructs a node."""
    loader, pkg = _load(tmpdir, NEEDS)
    b = _builder(tmpdir, loader, pkg)
    b.mkTaskNode("p.consumer-a")
    assert "p.img.prof" in b._task_node_m
    assert "p.img.opt" not in b._task_node_m


def test_an_unaddressed_cell_does_no_work(tmpdir):
    """End-to-end, not just graph shape: the sibling's body never executes."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - shell: bash
              run: touch ${{ rundir }}/../built-${{ this.build }}.txt
        - root: consumer
          uses: std.Message
          needs: [img.prof]
          with: {msg: c}
    ''')
    b = _builder(tmpdir, loader, pkg)
    _run(tmpdir, b.mkTaskNode("p.consumer"))
    rundir = os.path.join(str(tmpdir), "rundir")
    assert os.path.exists(os.path.join(rundir, "built-prof.txt"))
    assert not os.path.exists(os.path.join(rundir, "built-opt.txt"))


def test_a_cells_deferred_need_resolves_per_cell(tmpdir):
    """`needs: ["flags-${{ this.build }}"]` -- the idiom that lets one body
    parameterize over the variant without a hand-written task per cell."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - {name: flags-opt,  uses: std.Message, with: {msg: fopt}}
        - {name: flags-prof, uses: std.Message, with: {msg: fprof}}
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - uses: std.Message
              needs: ["flags-${{ this.build }}"]
              with: {msg: "img"}
    ''')
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.img.prof")
    assert "p.flags-prof" in [n.name for n, _ in node.needs]
    assert "p.flags-opt" not in b._task_node_m


def test_a_cell_runs_with_its_own_bindings(tmpdir):
    loader, pkg = _load(tmpdir, BASIC)
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.img.rtl.prof")
    _run(tmpdir, node)
    assert node.params.msg == "view=rtl build=prof"


# ---------------------------------------------------------------------------
# Load-time validation
# ---------------------------------------------------------------------------

def test_select_and_matrix_together_are_rejected(tmpdir):
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            matrix:
              a: [1, 2]
            select:
              axes:
                b: [x, y]
            body:
            - uses: std.Message
              with: {msg: hi}
    ''')
    assert msgs


def test_select_requires_exactly_one_body_task(tmpdir):
    """A cell IS an artifact; with two body tasks there is no answer to what
    `<family>.<key>` names."""
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                b: [x, y]
            body:
            - {uses: std.Message, with: {msg: one}}
            - {uses: std.Message, with: {msg: two}}
    ''')
    assert msgs


def test_an_empty_axis_is_a_marker(tmpdir):
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: []
            body:
            - {uses: std.Message, with: {msg: hi}}
    ''')
    assert any("non-empty list" in m for m in msgs)


def test_an_axis_referencing_an_unknown_variable_is_a_marker(tmpdir):
    """A family's shape is resolved at load, so an axis that cannot be resolved
    there is reported there -- naming the axis -- rather than failing later."""
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: "${{ nosuch }}"
            body:
            - {uses: std.Message, with: {msg: hi}}
    ''')
    assert any("select axis 'build'" in m for m in msgs)


def test_a_key_collision_is_a_marker(tmpdir):
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                a: [x, y]
                b: [p, q]
              key: "${{ this.a }}"
            body:
            - {uses: std.Message, with: {msg: hi}}
    ''')
    assert any("resolve to the key" in m for m in msgs)


def test_a_default_naming_a_non_axis_is_a_marker(tmpdir):
    msgs = _errors(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
              default: {nosuch: opt}
            body:
            - {uses: std.Message, with: {msg: hi}}
    ''')
    assert any("is not an axis" in m for m in msgs)


# ---------------------------------------------------------------------------
# Scale: expansion is cheap
# ---------------------------------------------------------------------------

def test_expansion_creates_tasks_not_nodes(tmpdir):
    """A 3x5 family is 15 Task objects and ZERO TaskNodes until one is asked
    for. This is what makes eager load-time expansion affordable."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                view: [a, b, c]
                build: [v, w, x, y, z]
            body:
            - uses: std.Message
              with: {msg: "${{ this.view }}${{ this.build }}"}
    ''')
    cells = [k for k in pkg.task_m if k.startswith("p.img.")]
    assert len(cells) == 15
    b = _builder(tmpdir, loader, pkg)
    assert not [k for k in b._task_node_m if k.startswith("p.img")]
    b.mkTaskNode("p.img.b.x")
    assert [k for k in b._task_node_m if k.startswith("p.img")] == ["p.img.b.x"]


# ---------------------------------------------------------------------------
# Cache identity
# ---------------------------------------------------------------------------

def test_cells_differing_only_in_a_need_are_distinct(tmpdir):
    """The sharpest collision risk: two cells whose PARAMS are identical and
    which differ only in which flag-holder they need. If the cache keyed on
    params alone these would collide -- and a collision here hands back the
    wrong binary, silently."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - {name: flags-opt,  uses: std.Message, with: {msg: fopt}}
        - {name: flags-prof, uses: std.Message, with: {msg: fprof}}
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - uses: std.Message
              needs: ["flags-${{ this.build }}"]
              with: {msg: "same-for-every-cell"}
    ''')
    b = _builder(tmpdir, loader, pkg)
    opt = b.mkTaskNode("p.img.opt")
    prof = b.mkTaskNode("p.img.prof")

    assert opt is not prof
    assert opt.name != prof.name
    # Identical params -- so name and needs are the whole difference.
    assert opt.params.msg == prof.params.msg
    assert [n.name for n, _ in opt.needs] != [n.name for n, _ in prof.needs]
    # ...and they must not share a rundir, which is what the cache keys off.
    assert opt.rundir != prof.rundir


def test_a_cells_rundir_does_not_depend_on_who_asked_for_it(tmpdir):
    """A shared artifact must land in the same place regardless of which
    consumer triggered its construction, or its identity moves with graph
    traversal order."""
    flow = '''\
    package:
        name: p
        tasks:
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - uses: std.Message
              with: {msg: img}
        - {name: consumer-a, uses: std.Message, needs: [img.prof], with: {msg: a}}
        - {name: consumer-b, uses: std.Message, needs: [img.prof], with: {msg: b}}
    '''
    loader, pkg = _load(tmpdir, flow)
    via_a = _builder(tmpdir, loader, pkg)
    via_a.mkTaskNode("p.consumer-a")
    rundir_a = via_a._task_node_m["p.img.prof"].rundir

    loader, pkg = _load(tmpdir, flow)
    via_b = _builder(tmpdir, loader, pkg)
    via_b.mkTaskNode("p.consumer-b")
    rundir_b = via_b._task_node_m["p.img.prof"].rundir

    assert rundir_a == rundir_b


# ---------------------------------------------------------------------------
# Regressions found by migrating a real project (fw-wb-dma)
# ---------------------------------------------------------------------------

def test_a_deferred_need_reaches_a_compound_bodys_input(tmpdir):
    """A compound consumes its dependencies through `input`, not `needs`.
    Deferred (per-cell) needs are wired after `_gatherNeeds` has already
    extended `input.needs`, so without an explicit append the interior compiles
    without the very thing the cell asked for.

    Only ever bit matrix bodies that were leaves; a select body is naturally a
    compound, which is what exposed it -- in the reference project as a
    simulation image built without its UVM library."""
    loader, pkg = _load(tmpdir, '''\
    package:
        name: p
        tasks:
        - {name: dep-opt,  uses: std.FileSet, with: {type: t, base: ".", include: ["*.opt"]}}
        - {name: dep-prof, uses: std.FileSet, with: {type: t, base: ".", include: ["*.prof"]}}
        - name: inner
          tasks:
          - {name: leaf, uses: std.Message, with: {msg: inner}}
        - name: img
          strategy:
            select:
              axes:
                build: [opt, prof]
            body:
            - uses: inner
              needs: ["dep-${{ this.build }}"]
    ''')
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.img.prof")
    assert "p.dep-prof" in [n.name for n, _ in node.needs]
    # The interior reads `input.needs`; that is the list that must carry it,
    # and the one the bug left empty.
    assert "p.dep-prof" in [n.name for n, _ in node.input.needs]
    # The sibling cell's dep is not pulled in.
    assert "p.dep-opt" not in [n.name for n, _ in node.input.needs]


def test_a_cell_key_resolves_inside_a_fragment(tmpdir):
    """A cell key is dotted AND local. Historically a dot meant "already
    qualified", so the fragment prefix was never tried and a perfectly local
    reference failed -- with a "did you mean" hint naming the very task it
    should have found."""
    d = str(tmpdir)
    os.makedirs(os.path.join(d, "sub"), exist_ok=True)
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(textwrap.dedent('''\
        package:
            name: p
            fragments:
            - sub/flow.dv
        '''))
    with open(os.path.join(d, "sub", "flow.dv"), "w") as f:
        f.write(textwrap.dedent('''\
        fragment:
            name: frag
            tasks:
            - name: img
              strategy:
                select:
                  axes:
                    build: [opt, prof]
                body:
                - uses: std.Message
                  with: {msg: "img"}
            - root: consumer
              uses: std.Message
              needs: [img.prof]
              with: {msg: c}
        '''))
    msgs = []
    loader, pkg = loadProjPkgDef(d, listener=lambda m: msgs.append(m.msg))
    assert not msgs, msgs
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.frag.consumer")
    assert [n.name for n, _ in node.needs] == ["p.frag.img.prof"]


def test_srcdir_in_a_cell_is_the_familys_directory(tmpdir):
    """A select cell has no parent node to set `srcdir` before its eval context
    is copied, so `${{ srcdir }}` fell through to the root package -- and a body
    whose parameter defaults from it looked for files in the wrong tree."""
    d = str(tmpdir)
    os.makedirs(os.path.join(d, "sub"), exist_ok=True)
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(textwrap.dedent('''\
        package:
            name: p
            fragments:
            - sub/flow.dv
        '''))
    with open(os.path.join(d, "sub", "flow.dv"), "w") as f:
        f.write(textwrap.dedent('''\
        fragment:
            name: frag
            tasks:
            - name: img
              strategy:
                select:
                  axes:
                    build: [opt, prof]
                body:
                - uses: std.Message
                  with: {msg: "${{ srcdir }}"}
        '''))
    loader, pkg = loadProjPkgDef(d)
    b = _builder(tmpdir, loader, pkg)
    node = b.mkTaskNode("p.frag.img.prof")
    assert node.params.msg == os.path.join(d, "sub")
