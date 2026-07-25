#****************************************************************************
#* test_elab_sees_overrides.py
#*
#* An elaborator decides how to build a node; it must decide from the value the
#* user actually asked for. `ctxt.mkParams()` therefore applies the full
#* precedence ladder -- default -> with:/kwargs -> -P -> -D -> --flag -- rather
#* than handing back declared defaults.
#*
#* Before this, `_apply_node_params` ran *after* the elaborator returned, so an
#* elaborator that read a parameter silently read its default. That is the same
#* mistake load-time `${{ }}` expansion made (docs/proposals/
#* expansion_phase_ladder.md): deciding at the one moment when values are
#* guaranteed not to be final.
#*
#* The motivating consumer is needs-pruning -- a `tests` root that filters which
#* cases enter the graph from a command-line selector (docs/test_tasks_plan.md).
#****************************************************************************
import os
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from .marker_collector import MarkerCollector


# The elaborator records what mkParams reported, then prunes needs by it.
_ELAB_MODULE = '''
SEEN = []

def select(ctxt, task, name):
    params = ctxt.mkParams(task)
    only = getattr(params, "only", None)
    SEEN.append(only)

    def _select(needs):
        if not only:
            return needs
        return [n for n in needs if n.name.rsplit(".", 1)[-1] in only]

    return ctxt.buildDefault(task, name, select_needs=_select)


def seen():
    return SEEN[-1] if SEEN else None
'''


FLOW = """\
package:
    name: p
    tasks:
    - { name: a, shell: bash, run: 'echo a' }
    - { name: b, shell: bash, run: 'echo b' }
    - { name: c, shell: bash, run: 'echo c' }
    - name: Base
      elaborate: elabsel:select
      with:
        only: { type: list, value: [] }
    - name: tests
      scope: root
      uses: Base
      needs: [a, b, c]
"""


@pytest.fixture
def env(tmpdir):
    """Load the flow with the elaborator module importable, and hand back a
    builder factory plus the (freshly imported) elaborator module."""
    d = str(tmpdir)
    with open(os.path.join(d, "elabsel.py"), "w") as f:
        f.write(_ELAB_MODULE)
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(FLOW)

    sys.path.insert(0, d)
    sys.modules.pop("elabsel", None)
    try:
        collector = MarkerCollector()
        pkg = PackageLoader(marker_listeners=[collector]).load(
            os.path.join(d, "flow.dv"))
        assert [m.msg for m in collector.markers] == []
        import elabsel

        def build(**builder_kw):
            elabsel.SEEN.clear()
            builder = TaskGraphBuilder(
                root_pkg=pkg, rundir=os.path.join(d, "rundir"), **builder_kw)
            node = builder.mkTaskNode("p.tests")
            kept = sorted(n.name for n, _ in node.needs)
            return elabsel.seen(), kept

        yield build
    finally:
        sys.path.remove(d)
        sys.modules.pop("elabsel", None)


# ------------------------------------------------ what the elaborator sees

def test_default_when_nothing_overrides(env):
    seen, kept = env()
    assert seen == []
    assert kept == ["p.a", "p.b", "p.c"]


def test_task_qualified_D(env):
    seen, kept = env(task_param_overrides={"p.tests": {"only": "b"}})
    assert seen == ["b"]
    assert kept == ["p.b"]


def test_bare_D(env):
    seen, kept = env(leaf_param_overrides={"only": "c"})
    assert seen == ["c"]
    assert kept == ["p.c"]


def test_comma_list_is_coerced_to_a_list(env):
    """`-D only=b,c` must reach the elaborator as a list. Reaching around
    mkParams into the raw override map -- the workaround this replaces --
    would have handed it the string 'b,c', and `'b' in 'b,c'` is a substring
    test that quietly matches the wrong things."""
    seen, kept = env(task_param_overrides={"p.tests": {"only": "b,c"}})
    assert seen == ["b", "c"]
    assert kept == ["p.b", "p.c"]


# ------------------------------------------------------------- precedence

def test_D_beats_the_declared_default(env):
    seen, _ = env(task_param_overrides={"p.tests": {"only": "a"}})
    assert seen == ["a"]


def test_task_qualified_D_beats_bare_D(env):
    """Same rung ordering the node settle path uses: an explicitly-targeted
    key wins over a bare one."""
    seen, kept = env(task_param_overrides={"p.tests": {"only": "a"}},
                     leaf_param_overrides={"only": "c"})
    assert seen == ["a"]
    assert kept == ["p.a"]


# --------------------------------------------------------------- pruning

def test_a_pruned_need_is_never_built(env):
    """Pruning happens before the need is resolved into a node, so the
    dropped task is absent from the graph -- not built-and-disabled as an
    `iff: false` stub would be. That is what makes deselecting a test also
    skip whatever only it needed."""
    _, kept = env(task_param_overrides={"p.tests": {"only": "b"}})
    assert kept == ["p.b"]


def test_selection_of_everything_is_the_same_graph(env):
    seen_all, kept_all = env()
    _, kept_explicit = env(task_param_overrides={"p.tests": {"only": "a,b,c"}})
    assert kept_explicit == kept_all == ["p.a", "p.b", "p.c"]


# ------------------------------------------------------- end to end (CLI)
# The builder-level tests above drive the override maps directly. These prove
# the rungs that only exist at the CLI -- `-P` and a `cli:` `--flag` -- travel
# the same path and reach the elaborator.

CLI_FLOW = """\
package:
    name: p
    tasks:
    - { name: a, shell: bash, run: 'echo a' }
    - { name: b, shell: bash, run: 'echo b' }
    - { name: c, shell: bash, run: 'echo c' }
    - name: tests
      scope: root
      elaborate: elabsel:select
      cli:
        args:
        - name: only
      with:
        only: { type: list, value: [] }
      needs: [a, b, c]
"""


def _cli_env(tmpdir, flow=CLI_FLOW):
    d = str(tmpdir)
    with open(os.path.join(d, "elabsel.py"), "w") as f:
        f.write(_ELAB_MODULE)
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(flow)
    return d


def _dfm(cwd, *args):
    import subprocess
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(cwd), capture_output=True, text=True, env=env)


def _ran(cwd):
    """Which case tasks actually produced a rundir."""
    rundir = os.path.join(str(cwd), "rundir")
    if not os.path.isdir(rundir):
        return []
    return sorted(n for n in os.listdir(rundir) if n in ("p.a", "p.b", "p.c"))


def test_cli_flag_reaches_the_elaborator(tmpdir):
    d = _cli_env(tmpdir)
    proc = _dfm(d, "run", "tests", "--only", "b")
    assert proc.returncode == 0, proc.stderr
    assert _ran(d) == ["p.b"]


def test_param_file_reaches_the_elaborator(tmpdir):
    d = _cli_env(tmpdir)
    with open(os.path.join(d, "p.json"), "w") as f:
        f.write('{"tasks": {"p.tests": {"only": ["c"]}}}')
    proc = _dfm(d, "run", "tests", "-P", "p.json")
    assert proc.returncode == 0, proc.stderr
    assert _ran(d) == ["p.c"]


def test_cli_flag_beats_D_at_elaboration(tmpdir):
    """The ladder's top two rungs, decided *during* elaboration rather than
    after it."""
    d = _cli_env(tmpdir)
    proc = _dfm(d, "run", "tests", "--only", "a", "-D", "p.tests.only=c")
    assert proc.returncode == 0, proc.stderr
    assert _ran(d) == ["p.a"]
