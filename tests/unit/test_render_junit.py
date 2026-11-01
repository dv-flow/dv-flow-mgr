"""JUnit and CTRF renderings of the shared results fixtures."""
import glob
import json
import os
import xml.etree.ElementTree as ET

import jsonschema
import pytest

from dv_flow.mgr.results.model import ResultsFile
from dv_flow.mgr.results.render_junit import ctrf_doc, render_junit

DATA = os.path.join(os.path.dirname(__file__), "data", "results")
FIXTURES = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(DATA, "*.json"))
                  if not os.path.basename(f).startswith("legacy-"))
TEST_FIXTURES = ["test-suite-pass", "test-suite-fail", "build-failure"]


def _rf(name):
    return ResultsFile.model_validate(json.load(open(os.path.join(DATA, name + ".json"))))


@pytest.mark.parametrize("name", FIXTURES)
def test_golden(name):
    with open(os.path.join(DATA, "junit", name + ".xml")) as f:
        assert render_junit(_rf(name)) == f.read()


@pytest.mark.parametrize("name", FIXTURES)
def test_well_formed(name):
    root = ET.fromstring(render_junit(_rf(name)))
    assert root.tag == "testsuites"
    n = sum(int(s.get("tests")) for s in root.findall("testsuite"))
    assert n == int(root.get("tests")) == len(root.findall(".//testcase"))


@pytest.mark.parametrize("name", TEST_FIXTURES)
def test_counts_match_summary(name):
    rf = _rf(name)
    root = ET.fromstring(render_junit(rf))
    c = rf.summary.counts
    assert int(root.get("tests")) == c["total"]
    assert int(root.get("failures")) == c["fail"]
    assert int(root.get("errors")) == c["error"] + c["timeout"]
    assert int(root.get("skipped")) == c["notrun"] + c["skip"]


def test_synth_timing_is_a_failed_testcase():
    root = ET.fromstring(render_junit(_rf("synth-timing-fail")))
    tc = {t.get("name"): t for t in root.iter("testcase")}
    assert set(tc) == {"timing", "area"}
    f = tc["timing"].find("failure")
    assert f is not None and "WNS -0.12 ns" in f.get("message")
    assert "wns_ns=-0.12" in f.text
    assert tc["area"].find("failure") is None


def test_notrun_is_skipped_naming_the_blocker():
    root = ET.fromstring(render_junit(_rf("build-failure")))
    sk = [t.find("skipped") for t in root.iter("testcase") if t.find("skipped") is not None]
    assert len(sk) == 2
    assert all("blocked: wb-dma-example.fw-build failed" in s.get("message") for s in sk)
    err = [t for t in root.iter("testcase") if t.find("error") is not None]
    assert [t.get("name") for t in err] == ["fw-build"]


def test_test_case_properties():
    root = ET.fromstring(render_junit(_rf("test-suite-fail")))
    tc = {t.get("name"): t for t in root.iter("testcase")}
    props = {p.get("name"): p.get("value") for p in tc["smoke"].iter("property")}
    assert props["sim"] == "vlt" and props["walltime_s"] == "12.5s"
    synth = ET.fromstring(render_junit(_rf("synth-timing-fail")))
    assert list(synth.iter("property")) == []      # only test cases carry them


def test_failure_has_checks_and_log():
    root = ET.fromstring(render_junit(_rf("test-suite-fail")))
    (t,) = [t for t in root.iter("testcase") if t.find("failure") is not None]
    assert t.get("name") == "two-ch"
    assert "check uvm_errors: fail" in t.find("failure").text
    assert t.find("system-out").text.endswith("sim.log:1873")


# -- CTRF ---------------------------------------------------------------------

def _ctrf_schema():
    with open(os.path.join(os.path.dirname(__file__), "data", "ctrf-schema-min.json")) as f:
        return json.load(f)


@pytest.mark.parametrize("name", FIXTURES)
def test_ctrf_validates(name):
    jsonschema.validate(ctrf_doc(_rf(name)), _ctrf_schema())


def test_ctrf_mapping():
    d = ctrf_doc(_rf("build-failure"), report_id="x")
    s = d["results"]["summary"]
    assert (s["tests"], s["passed"], s["failed"], s["skipped"]) == (4, 1, 1, 2)
    t = {x["name"]: x for x in d["results"]["tests"]}
    assert t["fw-build"]["rawStatus"] == "error" and t["fw-build"]["status"] == "failed"
    assert t["soc-dma-copy"]["status"] == "skipped"
    assert "blocked" in t["soc-dma-copy"]["message"]
    assert t["smoke"]["extra"]["walltime_s"] == 12.5
    assert t["smoke"]["extra"]["sim"] == "vlt"
    assert d["reportId"] == "x" and d["specVersion"] == "0.0.0"


# -- markdown -------------------------------------------------------------------

def test_markdown_summary():
    from dv_flow.mgr.results.render_md import render_md
    md = render_md(_rf("build-failure"))
    assert md.splitlines()[0] == "# 💥 wb-dma-example.tests: error"
    assert "| total | pass | error | notrun |" in md
    assert "`tests/_tasks/fw-build`: dma.c:41" in md
    assert "blocked: wb-dma-example.fw-build failed" in md
    md = render_md(_rf("synth-timing-fail"))
    assert "check `timing`: fail" in md
