#****************************************************************************
#* test_resolve_fallback.py
#*
#* Tests for the resolve() package fall-through (Feature B): after a `let:`
#* miss, resolve() walks the instance task's `uses`-chain packages (most-derived
#* first) before the literal default. See
#* docs/proposals/task_elaboration_impl_plan.md §B.
#****************************************************************************
import os
import asyncio
import pytest
from typing import List
from dv_flow.mgr.expr_eval import ExprEval, ResolveError
from dv_flow.mgr.param_ref_eval import ParamRefEval
from dv_flow.mgr.param_builder import ParamBuilder
from dv_flow.mgr.param_def import ParamDef
from dv_flow.mgr.task import Task
from dv_flow.mgr.package import Package
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


class FakeResolver:
    """Stub VarResolver exposing pkg_var over an in-memory {pkg: {name: value}}
    map, so the walk order can be exercised without YAML plumbing."""
    def __init__(self, pkg_vars):
        self.pkg_vars = pkg_vars

    def pkg_var(self, pkg_name, name):
        d = self.pkg_vars.get(pkg_name, {})
        if name in d:
            return True, d[name]
        return False, None

    def resolve_variable(self, name):
        return None


def _mk_chain(*pkg_names):
    """Build an instance Task whose `uses` chain visits the given packages in
    order. Returns the most-derived (instance) task."""
    pkgs = {}
    task = None
    prev = None
    for i, pname in enumerate(pkg_names):
        pkg = pkgs.setdefault(pname, Package(name=pname))
        t = Task(name="%s.T%d" % (pname, i), package=pkg, uses=prev)
        prev = t
    return prev


def _resolve(task, pkg_vars, expr, let=None):
    """Drive resolve() through ParamBuilder so the `uses`-chain packages are
    threaded into ExprEval exactly as they are during a real build."""
    ev = ParamRefEval()
    ev.expr_eval.set_name_resolution(FakeResolver(pkg_vars))
    if let is not None:
        ev.expr_eval.variables['__let__'] = let
    pb = ParamBuilder(ev)
    merged = {'sim': (ParamDef(value=expr), str)}
    result = pb._evaluate_params(merged, task.name, task)
    return result['sim'][1]


# --- Chain construction (B.3) -------------------------------------------------

def test_uses_chain_pkg_names_order():
    # foo.run-sim uses hdlsim.SimRun -> chain packages [foo, hdlsim]
    pkg_foo = Package(name='foo')
    pkg_hdlsim = Package(name='hdlsim')
    base = Task(name='hdlsim.SimRun', package=pkg_hdlsim)
    inst = Task(name='foo.run-sim', package=pkg_foo, uses=base)
    pb = ParamBuilder(ParamRefEval())
    assert pb._uses_chain_pkg_names(inst) == ['foo', 'hdlsim']


def test_uses_chain_pkg_names_dedup():
    # foo.run -> foo.Base -> hdlsim.SimRun : 'foo' appears once, order preserved
    pkg_foo = Package(name='foo')
    pkg_hdlsim = Package(name='hdlsim')
    base = Task(name='hdlsim.SimRun', package=pkg_hdlsim)
    mid = Task(name='foo.Base', package=pkg_foo, uses=base)
    inst = Task(name='foo.run', package=pkg_foo, uses=mid)
    pb = ParamBuilder(ParamRefEval())
    assert pb._uses_chain_pkg_names(inst) == ['foo', 'hdlsim']


# --- Precedence ladder (B.1) --------------------------------------------------

def test_let_wins_over_pkg_vars():
    # Case 1: let: sim=mti + foo.sim=vlt + hdlsim.sim=xsm -> mti (let wins)
    inst = _mk_chain('hdlsim', 'foo')  # instance task's chain = [foo, hdlsim]
    assert _resolve(inst,
                    {'foo': {'sim': 'vlt'}, 'hdlsim': {'sim': 'xsm'}},
                    "${{ resolve('sim', 'unset') }}",
                    let={'sim': 'mti'}) == 'mti'


def test_instance_pkg_shadows_base():
    # Case 2: no let; foo.sim=vlt + hdlsim.sim=xsm -> vlt (walk order: foo first)
    inst = _mk_chain('hdlsim', 'foo')
    assert _resolve(inst,
                    {'foo': {'sim': 'vlt'}, 'hdlsim': {'sim': 'xsm'}},
                    "${{ resolve('sim', 'unset') }}") == 'vlt'


def test_next_pkg_in_walk():
    # Case 3: no let; no foo.sim; hdlsim.sim=xsm -> xsm (fall to next pkg)
    inst = _mk_chain('hdlsim', 'foo')
    assert _resolve(inst,
                    {'hdlsim': {'sim': 'xsm'}},
                    "${{ resolve('sim', 'unset') }}") == 'xsm'


def test_literal_default_last():
    # Case 4: nothing set anywhere -> literal 'unset' (last resort)
    inst = _mk_chain('hdlsim', 'foo')
    assert _resolve(inst, {}, "${{ resolve('sim', 'unset') }}") == 'unset'


def test_deeper_chain_reaches_third_pkg():
    # Case 7: foo.run -> bar.Base -> hdlsim.SimRun, only hdlsim.sim set
    inst = _mk_chain('hdlsim', 'bar', 'foo')  # chain = [foo, bar, hdlsim]
    assert _resolve(inst,
                    {'hdlsim': {'sim': 'xsm'}},
                    "${{ resolve('sim', 'unset') }}") == 'xsm'


def test_back_compat_default_when_no_var_named():
    # Case 9: resolve('vlt') back-compat -- no 'sim' var anywhere, default used.
    inst = _mk_chain('hdlsim', 'foo')
    assert _resolve(inst,
                    {'foo': {'other': 'x'}},
                    "${{ resolve('sim', 'vlt') }}") == 'vlt'


def test_no_default_no_binding_errors():
    # No let, no pkg var, no default -> ResolveError surfaced by param_builder.
    inst = _mk_chain('hdlsim', 'foo')
    # 0-arg resolve() -> name is the current param 'sim', no default -> error.
    with pytest.raises(Exception) as ei:
        _resolve(inst, {}, "${{ resolve() }}")
    assert "parameter 'sim'" in str(ei.value)


def test_pkg_var_falsey_value_is_found():
    # A package var whose value is falsey ("") must still count as "found" and
    # win over the default -- (found, value) tuple, not value-or-None.
    inst = _mk_chain('hdlsim', 'foo')
    assert _resolve(inst,
                    {'foo': {'sim': ''}},
                    "${{ resolve('sim', 'unset') }}") == ''


# --- Integration: package-level var + instance override (B.2) -----------------

def _run(tmpdir, flow_dv, taskname, capsys, set_param=None):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector)
    if set_param is not None:
        builder.setParam(*set_param)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode(taskname)
    asyncio.run(runner.run(task))
    return capsys.readouterr().out, collector


_PKG_VAR_FLOW = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: "unset"
  tasks:
  - name: Run
    uses: std.Message
    with:
      msg: "SIM=${{ resolve('sim', 'literal') }}"
'''


# Case 5 (single-package form): resolve() backstops on the package-level var,
# read from the *instance* params so a runtime override is honored.
def test_pkg_var_backstop(tmpdir, capsys):
    out, _ = _run(tmpdir, _PKG_VAR_FLOW, "foo.Run", capsys)
    assert "SIM=unset" in out       # package default, not the resolve() literal


def test_pkg_var_instance_override(tmpdir, capsys):
    out, _ = _run(tmpdir, _PKG_VAR_FLOW, "foo.Run", capsys,
                  set_param=("sim", "vlt"))
    assert "SIM=vlt" in out         # instance override (B.2) beats class default
