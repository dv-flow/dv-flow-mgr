"""The fixture's synthesis task: yosys `stat -json` and a nextpnr log ->
a `yosys.SynthResult` with `synth` and `pnr` stage children."""
import json
import os
import re
import shutil
import subprocess

from dv_flow.mgr import TaskDataResult
from dv_flow.mgr.results import api as R

_FMAX_RE = re.compile(r"Max frequency for clock '([^']*)': ([0-9.]+) MHz(?: \((PASS|FAIL) at ([0-9.]+) MHz\))?")
_LC_RE = re.compile(r"ICESTORM_LC:\s+(\d+)/\s*(\d+)")


def parse_stat(path):
    with open(path) as f:
        d = json.load(f)["design"]
    by = d.get("num_cells_by_type", {})
    luts = sum(v for k, v in by.items() if "LUT" in k)
    ffs = sum(v for k, v in by.items() if "DFF" in k)
    brams = sum(v for k, v in by.items() if "RAM" in k)
    return {"cells": d.get("num_cells", 0), "luts": luts, "ffs": ffs, "brams": brams}


def parse_nextpnr(path):
    ret = {}
    with open(path) as f:
        for line in f:
            m = _FMAX_RE.search(line)
            if m:
                ret["clock"] = m.group(1).split("$")[0]
                ret["fmax_mhz"] = float(m.group(2))
            m = _LC_RE.search(line)
            if m:
                ret["lcs"] = int(m.group(1))
    return ret


def _stage(ctxt, name, metrics, log, reports=()):
    s = R.mk_result(ctxt, "yosys.SynthResult", name=name, metrics=metrics)
    s.artifacts.append(R.artifact(ctxt, log, role="log", filetype="%sLog" % name))
    for path, label in reports:
        s.artifacts.append(R.artifact(ctxt, path, role="report", label=label))
    R.finish(s)
    return s


async def Synth(ctxt, input):
    p = input.params
    rd = input.rundir
    cap = p.captured
    if p.real and shutil.which("yosys"):
        src = os.path.join(input.srcdir, "design.v")
        subprocess.check_call(["yosys", "-q", "-l", "yosys.log", "-p",
                               "read_verilog %s; synth_ice40 -top counter; "
                               "tee -q -o stat.json stat -json" % src], cwd=rd)
        stat, ylog = os.path.join(rd, "stat.json"), os.path.join(rd, "yosys.log")
    else:
        for f in ("stat.json", "yosys.log"):
            shutil.copy(os.path.join(cap, f), rd)
        stat, ylog = os.path.join(rd, "stat.json"), os.path.join(rd, "yosys.log")
    shutil.copy(os.path.join(cap, "nextpnr.log"), rd)
    plog = os.path.join(rd, "nextpnr.log")

    sm = parse_stat(stat)
    pm = parse_nextpnr(plog)
    synth_m = {k: R.metric(v, name=k) for k, v in sm.items()}
    pnr_m = {}
    if "fmax_mhz" in pm:
        pnr_m["fmax_mhz"] = R.metric(pm["fmax_mhz"], name="fmax_mhz")

    metrics = dict(synth_m)
    metrics.update(pnr_m)
    if "fmax_mhz" in pm:
        wns = round(1000.0 / p.fmax_mhz - 1000.0 / pm["fmax_mhz"], 3)
        metrics["wns_ns"] = R.metric(wns, name="wns_ns")

    res = R.mk_result(ctxt, "yosys.SynthResult", name="synth",
                      attrs={"top": p.top, "part": p.part}, metrics=metrics)
    res.tool = {"name": "yosys"}
    res.checks.append(R.eval_check(metrics, "timing", "wns_ns", ">=", 0))
    res.checks.append(R.eval_check(metrics, "area", "luts", "<=", p.max_luts))
    res.children = [_stage(ctxt, "synth", synth_m, ylog),
                    _stage(ctxt, "pnr", pnr_m, plog, [(plog, "Timing")])]
    res.artifacts.append(R.artifact(ctxt, plog, role="report", label="Timing"))
    R.finish(res)
    if res.checks[0]["status"] == "fail":
        res.msg = "timing not met: WNS %s ns on %s (target %g MHz)" % (
            metrics["wns_ns"]["value"], pm.get("clock", "?"), p.fmax_mhz)
    return TaskDataResult(output=[res])


async def UnitTest(ctxt, input):
    r = R.mk_result(ctxt, "std.TestResult", name="unit")
    R.finish(r)
    return TaskDataResult(output=[r])


async def Formal(ctxt, input):
    r = R.mk_result(ctxt, "yosys.FormalResult", name="bmc",
                    metrics={"depth": R.metric(20, name="depth")})
    r.checks.append(R.check("assertions", "pass", "failed", "==", 0, value=0))
    R.finish(r)
    return TaskDataResult(output=[r])
