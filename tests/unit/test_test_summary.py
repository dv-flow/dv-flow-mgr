#****************************************************************************
#* test_test_summary.py
#*
#* The end-of-run test report (`std.TestRunner`'s `summary:`).
#*
#* It reads verdicts structurally rather than by type, so a simulator, a formal
#* engine, and a lint task can all feed the same report. These tests therefore
#* drive it with plain stand-ins rather than any producer's real item types.
#****************************************************************************
import dataclasses as dc
from typing import Any, List

import pytest

from dv_flow.mgr.std import test_summary as ts
from dv_flow.mgr.summary_ctxt import render_renderable_to_text


@dc.dataclass
class Case:
    name : str = "c"
    passed : bool = True
    status : str = "pass"
    errors : int = 0
    sim : str = "vlt"
    walltime_s : float = 0.0


@dc.dataclass
class Rollup:
    total : int = 0
    passed : int = 0
    failed : int = 0
    errored : int = 0
    results : List[Any] = dc.field(default_factory=list)


class Ctxt:
    """Enough of SummaryCtxt for the renderer."""
    def __init__(self, output, detail="normal"):
        self.output = output
        self.root = type("N", (), {"params": type("P", (), {"detail": detail})()})()

    def task_summary(self):
        return "[GENERIC-TASK-SUMMARY]"


def _text(ctxt):
    value = ts.test_summary(ctxt)
    if isinstance(value, str):
        return value
    return render_renderable_to_text(value)


# ------------------------------------------------------------- classification

def test_a_case_and_a_rollup_are_told_apart():
    assert ts._is_case(Case()) is True
    assert ts._is_rollup(Case()) is False
    assert ts._is_rollup(Rollup()) is True
    assert ts._is_case(Rollup()) is False


def test_rollup_members_are_preferred_over_loose_cases():
    """A roll-up carries its members by value, so counting both would double
    every case."""
    case = Case(name="a")
    cases, rollups = ts.collect_cases([Rollup(total=1, passed=1, results=[case]), case])
    assert cases == [case]
    assert len(rollups) == 1


def test_counts_come_from_the_rollup_when_present():
    """The producer knows what 'errored' means; a structural guess does not."""
    r = Rollup(total=5, passed=3, failed=1, errored=1)
    assert ts.tally([], [r]) == (5, 3, 1, 1)


def test_counts_are_derived_when_there_is_no_rollup():
    cases = [Case(passed=True), Case(passed=False, status="fail"),
             Case(passed=False, status="timeout")]
    assert ts.tally(cases, []) == (3, 1, 1, 1)


# ----------------------------------------------------------------- rendering

def test_headline_counts_are_rendered():
    out = _text(Ctxt([Rollup(total=4, passed=3, failed=1,
                             results=[Case(name="bad", passed=False,
                                           status="fail", errors=2)])]))
    assert "3/4 passed" in out
    assert "1 failed" in out


def test_normal_detail_shows_failures_only():
    out = _text(Ctxt([Rollup(total=2, passed=1, failed=1, results=[
        Case(name="good", passed=True),
        Case(name="bad", passed=False, status="fail")])]))
    assert "bad" in out
    assert "good" not in out


def test_full_detail_shows_every_case_and_the_generic_summary():
    out = _text(Ctxt([Rollup(total=2, passed=1, failed=1, results=[
        Case(name="good", passed=True),
        Case(name="bad", passed=False, status="fail")])], detail="full"))
    assert "good" in out and "bad" in out
    assert "GENERIC-TASK-SUMMARY" in out


def test_quiet_detail_shows_no_case_rows():
    out = _text(Ctxt([Rollup(total=2, passed=1, failed=1, results=[
        Case(name="bad", passed=False, status="fail")])], detail="quiet"))
    assert "1/2 passed" in out
    assert "bad" not in out


def test_an_all_passing_run_says_so():
    out = _text(Ctxt([Rollup(total=2, passed=2, results=[
        Case(name="a"), Case(name="b")])]))
    assert "2/2 passed" in out
    assert "all cases passed" in out


def test_no_verdicts_falls_back_to_the_generic_summary():
    """A run that produced no test items is not an error here -- the *gate*
    decides that. A summary must never change the verdict."""
    assert ts.test_summary(Ctxt([])) == "[GENERIC-TASK-SUMMARY]"


def test_an_unknown_detail_level_degrades_to_normal():
    out = _text(Ctxt([Rollup(total=1, passed=0, failed=1, results=[
        Case(name="bad", passed=False, status="fail")])], detail="bogus"))
    assert "bad" in out


def test_loose_cases_without_a_rollup_still_render():
    out = _text(Ctxt([Case(name="a", passed=True),
                      Case(name="b", passed=False, status="fail")]))
    assert "1/2 passed" in out
    assert "b" in out


# ------------------------------------------------------- resource columns

@dc.dataclass
class StatCase(Case):
    """A case that also publishes a `stats` measurement map."""
    stats : dict = dc.field(default_factory=dict)


def test_duration_formatting_stays_readable_at_every_scale():
    # '%.1fs' would render all of these as '0.0s' -- the range short unit
    # tests actually live in.
    assert ts._fmt_secs(0.0099) == "9.9ms"
    assert ts._fmt_secs(0.000056) == "56us"
    assert ts._fmt_secs(5.28) == "5.3s"
    assert ts._fmt_secs(125) == "2m05s"
    # Unmeasured stays blank rather than becoming a plausible-looking zero.
    assert ts._fmt_secs(0) == "" and ts._fmt_secs(None) == ""


def test_simtime_prefers_the_value_the_tool_printed():
    assert ts._fmt_simtime({"simtime": "608us", "simtime_s": 6.08e-4}) == "608us"
    assert ts._fmt_simtime({"simtime_s": 1.5e-3}) == "1.5ms"
    assert ts._fmt_simtime({}) == ""


def test_peak_memory_falls_back_to_the_tool_reported_figure():
    assert ts._fmt_mem({"maxrss_mb": 412.0, "sim_mem_mb": 396.0}) == "412MB"
    assert ts._fmt_mem({"sim_mem_mb": 396.0}) == "396MB"
    assert ts._fmt_mem({}) == ""


def test_full_detail_shows_simtime_wall_and_peak_memory():
    out = _text(Ctxt([Rollup(total=1, passed=1, results=[
        StatCase(name="arb", walltime_s=5.28,
                 stats={"simtime": "608us", "maxrss_mb": 412.0})])],
        detail="full"))
    assert "608us" in out
    assert "5.3s" in out
    assert "412MB" in out
    # A header, since bare durations and sizes side by side are ambiguous.
    assert "simtime" in out and "peak-mem" in out


def test_resource_columns_are_omitted_when_nobody_reported_them():
    # A lint or formal producer publishes no stats: no empty columns, no header.
    out = _text(Ctxt([Rollup(total=1, passed=0, failed=1, results=[
        Case(name="bad", passed=False, status="fail")])]))
    assert "bad" in out
    assert "peak-mem" not in out and "simtime" not in out


def test_a_case_without_stats_still_renders_alongside_one_with_stats():
    out = _text(Ctxt([Rollup(total=2, passed=2, results=[
        StatCase(name="a", walltime_s=1.0, stats={"maxrss_mb": 100.0}),
        Case(name="b", walltime_s=2.0)])], detail="full"))
    assert "100MB" in out
    assert "a" in out and "b" in out


def test_speed_is_rendered_the_way_simulators_report_it():
    # A bare ratio (8.7e-05) says nothing at a glance; '87us/s' says the run
    # covers 87us of design time per wall second.
    assert ts._fmt_speed({"sim_speed_s_per_s": 8.7e-5}) == "87us/s"
    assert ts._fmt_speed({"sim_speed_s_per_s": 1.5}) == "1.5s/s"
    # Derived when the producer did not precompute it.
    assert ts._fmt_speed({"simtime_s": 34e-6, "walltime_s": 0.391}) == "87us/s"
    # Not derivable -> blank, not zero.
    assert ts._fmt_speed({"simtime_s": 34e-6}) == ""
    assert ts._fmt_speed({}) == ""


def test_full_detail_shows_the_speed_column():
    out = _text(Ctxt([Rollup(total=1, passed=1, results=[
        StatCase(name="sw_copy", walltime_s=0.391,
                 stats={"simtime": "34us", "simtime_s": 34e-6,
                        "walltime_s": 0.391, "maxrss_mb": 20.0})])],
        detail="full"))
    assert "speed" in out
    assert "87us/s" in out
