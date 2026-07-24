#****************************************************************************
#* test_resolve_builtin.py
#*
#* Tests for the resolve() expression builtin (scoped-variable read side).
#* See docs/proposals/scoped_variables_impl_plan.md §A1.4.
#****************************************************************************
import pytest
from dv_flow.mgr.expr_eval import ExprEval, ResolveError
from dv_flow.mgr.param_ref_eval import ParamRefEval
from dv_flow.mgr.param_builder import ParamBuilder
from dv_flow.mgr.param_def import ParamDef
from typing import List


def _eval(expr, current_param_name=None, let=None):
    ev = ExprEval()
    ev.current_param_name = current_param_name
    if let is not None:
        ev.variables['__let__'] = let
    return ev.eval(expr)


def test_resolve_default_no_scope():
    # Case 1: resolve('vlt'), no __let__ -> default 'vlt'
    assert _eval("resolve('vlt')", current_param_name='sim') == 'vlt'


def test_resolve_scoped_binding_wins_over_default():
    # Case 2: resolve('vlt') with __let__={'sim':'mti'}, current param 'sim' -> 'mti'
    assert _eval("resolve('vlt')", current_param_name='sim',
                 let={'sim': 'mti'}) == 'mti'


def test_resolve_explicit_name_binding_present():
    # Case 3: resolve('sim','vlt') explicit name, binding present -> bound value
    assert _eval("resolve('sim', 'vlt')", let={'sim': 'mti'}) == 'mti'


def test_resolve_explicit_name_uses_default():
    # resolve('sim','vlt') explicit name, no binding -> default
    assert _eval("resolve('sim', 'vlt')") == 'vlt'


def test_resolve_zero_arg_binding_present():
    # Case 4: resolve() (0-arg), binding present -> bound value
    assert _eval("resolve()", current_param_name='sim', let={'sim': 'mti'}) == 'mti'


def test_resolve_zero_arg_no_binding_errors():
    # Case 5: resolve() (0-arg), no binding -> ResolveError
    with pytest.raises(ResolveError):
        _eval("resolve()", current_param_name='sim')


def test_resolve_implicit_name_outside_param_context_errors():
    # Case 6: resolve('vlt') where current_param_name is None -> ResolveError
    with pytest.raises(ResolveError) as ei:
        _eval("resolve('vlt')", current_param_name=None)
    assert "implicit parameter name" in str(ei.value)


def test_resolve_too_many_args_errors():
    # Case 7: resolve('a','b','c') (3 args) -> ResolveError (arity)
    with pytest.raises(ResolveError):
        _eval("resolve('a', 'b', 'c')", current_param_name='sim')


def test_resolve_list_value_keeps_type():
    # Case 8: a scoped list value flows through coerce_to_kind for a list-typed
    # param and keeps its list type (dfm treats a bare string as an accepted
    # alternate for a list, so only native lists exercise real coercion).
    ev = ParamRefEval()
    ev.expr_eval.variables['__let__'] = {'opts': ['-O3', '-g']}
    builder = ParamBuilder(ev)
    merged = {
        'opts': (ParamDef(value="${{ resolve('opts', '-O0') }}"), List[str]),
    }
    result = builder._evaluate_params(merged, 'T')
    ptype, value = result['opts']
    assert value == ['-O3', '-g']


def test_resolve_error_not_swallowed_in_param_builder():
    # Case 9: resolve() inside _evaluate_params with no binding + no default
    # must raise (not swallowed to the literal string).
    ev = ParamRefEval()
    builder = ParamBuilder(ev)
    merged = {
        # 0-arg resolve with no binding -> ResolveError -> surfaced
        'sim': (ParamDef(value="${{ resolve() }}"), str),
    }
    with pytest.raises(Exception) as ei:
        builder._evaluate_params(merged, 'T')
    # Message should carry task/param context
    assert "parameter 'sim'" in str(ei.value)


def test_resolve_registered_method():
    # Smoke: resolve is a registered builtin
    ev = ExprEval()
    assert 'resolve' in ev.methods
