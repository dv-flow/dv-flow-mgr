#****************************************************************************
#* test_expr_parse_cache.py
#*
#* Phase 0 of run_body_expansion_plan.md: the expression parser and the ASTs
#* it produces are shared rather than rebuilt per reference.
#****************************************************************************
import time

import pytest

from dv_flow.mgr import expr_parser
from dv_flow.mgr.expr_parser import (
    ExprParser, parse_expr, clear_parse_cache)
from dv_flow.mgr.param_ref_eval import ParamRefEval


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_parse_cache()
    yield
    clear_parse_cache()


def test_parser_instance_is_shared():
    assert ExprParser.inst() is ExprParser.inst()


def test_same_text_returns_the_same_ast():
    a = parse_expr("a.b")
    b = parse_expr("a.b")
    assert a is b


def test_different_text_returns_different_asts():
    assert parse_expr("a") is not parse_expr("b")


def test_cached_ast_equals_a_cold_parse():
    """A cache hit must be indistinguishable from parsing afresh."""
    cold = ExprParser().parse("a + b * 2")
    warm = parse_expr("a + b * 2")
    assert warm == cold


def test_cache_hit_evaluates_to_the_same_value():
    e = ParamRefEval()
    e.set("a", "1")
    first = e.eval("v=${{ a }}")
    second = e.eval("v=${{ a }}")
    assert first == second == "v=1"


def test_evaluation_does_not_mutate_the_cached_ast():
    """ASTs are shared, so a visitor that mutated one would corrupt every
    later evaluation of the same text. ExprHId is the node with a mutable
    field (its id list), so it is the one worth pinning."""
    e = ParamRefEval()
    e.set("env", {"CC": "gcc"})
    before = parse_expr("env.CC")
    assert e.eval("${{ env.CC }}") == "gcc"
    after = parse_expr("env.CC")
    assert after is before
    assert after.id == ["env", "CC"]
    # ...and a second evaluation still works, which it would not if the
    # first had consumed the node's id list.
    assert e.eval("${{ env.CC }}") == "gcc"


def test_cache_is_bounded():
    for i in range(expr_parser._PARSE_CACHE_MAX + 10):
        parse_expr("n%d" % i)
    assert len(expr_parser._parse_cache) <= expr_parser._PARSE_CACHE_MAX


def test_clear_parse_cache_empties_it():
    parse_expr("a")
    assert expr_parser._parse_cache
    clear_parse_cache()
    assert not expr_parser._parse_cache


def test_repeated_eval_is_cheap():
    """Guard on the regression this phase exists to fix: constructing an
    ExprParser costs ~221us, so a per-reference rebuild put a 3-reference
    string at ~580us. Threshold is deliberately loose (~50x headroom over
    the ~2us measured) so this fails only on a real reintroduction."""
    e = ParamRefEval()
    e.set("a", "1")
    e.set("b", "2")
    e.set("c", "3")
    s = "x=${{ a }} y=${{ b }} z=${{ c }}"
    e.eval(s)  # warm

    n = 200
    start = time.perf_counter()
    for _ in range(n):
        e.eval(s)
    per_eval_us = (time.perf_counter() - start) / n * 1e6

    assert per_eval_us < 100, (
        "%.1fus per eval of a 3-reference string; the parser or AST cache "
        "is likely being bypassed" % per_eval_us)
