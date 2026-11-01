"""The results.json contract: the checked-in schema is current, and every
shared fixture validates against it (and is self-consistent)."""
import copy
import glob
import json
import os

import jsonschema
import pytest

import dv_flow.mgr
from dv_flow.mgr.results.model import ResultsFile, results_json_schema
from dv_flow.mgr.results.summary import compute_summary

DATA = os.path.join(os.path.dirname(__file__), "data", "results")
FIXTURES = sorted(f for f in glob.glob(os.path.join(DATA, "*.json"))
                  if not os.path.basename(f).startswith("legacy-"))


def _schema():
    p = os.path.join(os.path.dirname(os.path.abspath(dv_flow.mgr.__file__)),
                     "share", "dvflow-results.schema.json")
    with open(p) as f:
        return json.load(f)


def _load(p):
    with open(p) as f:
        return json.load(f)


def test_checked_in_schema_is_current():
    assert results_json_schema() == _schema(), (
        "dvflow-results.schema.json is out of date -- regenerate with "
        "`dfm util schema --results -o src/dv_flow/mgr/share/dvflow-results.schema.json`")


def test_fixtures_exist():
    names = {os.path.basename(f) for f in FIXTURES}
    for n in ("test-suite-pass.json", "test-suite-fail.json", "build-failure.json",
              "synth-timing-fail.json", "formal-cex.json", "mixed-root.json"):
        assert n in names


@pytest.mark.parametrize("path", FIXTURES, ids=os.path.basename)
def test_fixture_validates(path):
    jsonschema.validate(_load(path), _schema())


@pytest.mark.parametrize("path", FIXTURES, ids=os.path.basename)
def test_fixture_summary_is_consistent(path):
    """A fixture's summary is what dfm would compute from its result tree."""
    d = _load(path)
    rf = ResultsFile.model_validate(d)
    wt = d["summary"]["metrics"].get("walltime_s", {}).get("value")
    got = compute_summary(rf.result, wt).model_dump(exclude_none=True, mode="json")
    for f in got["failures"]:
        if not f.get("checks"):
            f.pop("checks", None)
    assert got == d["summary"]


def test_bad_status_fails_validation():
    d = _load(os.path.join(DATA, "test-suite-fail.json"))
    d["result"]["children"][0]["status"] = "bogus"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(d, _schema())


def test_missing_schema_key_fails_validation():
    d = _load(os.path.join(DATA, "test-suite-pass.json"))
    del d["schema"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(d, _schema())


def test_wrong_schema_version_fails_validation():
    d = _load(os.path.join(DATA, "test-suite-pass.json"))
    d["schema"] = "dvflow-results/2"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(d, _schema())


def test_cli_emits_results_schema(capsys):
    from dv_flow.mgr.util.cmds.cmd_schema import CmdSchema

    class A:
        output = "-"
        generate = False
        results = True
    CmdSchema()(A())
    out = json.loads(capsys.readouterr().out)
    assert out["$id"] == "https://dv-flow.github.io/dvflow-results.schema.json"
    assert out == _schema()
