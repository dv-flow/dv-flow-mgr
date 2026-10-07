#****************************************************************************
#* test_cli_flag_reload.py
#*
#* A project-level `cli:` flag reaches a REGISTERED base package exactly as
#* the `-D` it stands for does.
#*
#* `dfm run` loads the project once to learn its `cli:` flags, then reloads
#* it with their values. A package found through the extension registry
#* (DV_FLOW_PATH, a plugin) is served by a process-wide provider, and that
#* provider used to hand the reload the package it built during the FIRST
#* load -- built without the flag. Everything resolved while loading the base
#* then kept its default: a `${{ var }}` in an inherited task's `needs:`, and
#* the base's own variable defaults. `-D` worked because it is known before
#* the first load, which made `--build dbg` and `-D build=dbg` mean different
#* things.
#****************************************************************************
import json
import os
import subprocess
import sys
import textwrap

import pytest


BASE = '''\
package:
    name: cfgbase
    with:
      variant:
        type: str
        value: opt
        cli: true
        values: [opt, dbg]
    tasks:
    - {name: holder-opt, uses: std.Message, with: {msg: "holder is opt"}}
    - {name: holder-dbg, uses: std.Message, with: {msg: "holder is dbg"}}
    # Resolved while the base loads: the case the stale package got wrong.
    - name: bundle
      passthrough: all
      needs: ["holder-${{ variant }}"]
'''

# A second registered package that only DECLARES the same variable -- an
# unqualified override binds every package declaring the name -- and reads it
# as the default of a type field, the way a library's request type follows
# its own package variable. That default is fixed when the package loads.
OTHER = '''\
package:
    name: cfgother
    with:
      variant:
        type: str
        value: opt
    types:
    - name: Req
      with:
        level:
          type: str
          value: "${{ cfgother.variant }}"
'''

LEAF = '''\
package:
    name: leaf
    uses: cfgbase
    imports:
    - cfgbase
    - cfgother
    tasks:
    - root: req
      uses: cfgother.Req
'''


@pytest.fixture
def proj(tmp_path):
    for name, text in (("cfgbase", BASE), ("cfgother", OTHER)):
        (tmp_path / "pkgs" / name).mkdir(parents=True)
        (tmp_path / "pkgs" / name / "flow.dv").write_text(textwrap.dedent(text))
    (tmp_path / "leaf").mkdir()
    (tmp_path / "leaf" / "flow.dv").write_text(textwrap.dedent(LEAF))
    return tmp_path


# Registers the two packages the way a plugin's `dvfm_packages` does, then
# runs dfm's main in the same process, so they are served by ExtRgy providers.
_RUNNER = """\
import sys
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.package_provider_yaml import PackageProviderYaml
from dv_flow.mgr.__main__ import main
rgy = ExtRgy.inst()
for name, path in [(n, p) for n, p in zip(sys.argv[1::2], sys.argv[2::2])][:2]:
    rgy._pkg_m[name] = PackageProviderYaml(path=path)
sys.argv = ["dfm"] + sys.argv[5:]
main()
"""


def _dfm(proj, *args):
    pkgs = proj / "pkgs"
    return subprocess.run(
        [sys.executable, "-c", _RUNNER,
         "cfgbase", str(pkgs / "cfgbase" / "flow.dv"),
         "cfgother", str(pkgs / "cfgother" / "flow.dv"),
         "run"] + list(args),
        cwd=str(proj / "leaf"), capture_output=True, text=True)


def _needs_run(proj):
    """Names of the holder tasks that actually ran."""
    rundir = proj / "leaf" / "rundir"
    return sorted(d for d in os.listdir(rundir) if "holder-" in d)


@pytest.mark.parametrize("args", [
    ["--variant", "dbg"],
    ["-D", "variant=dbg"],
])
def test_a_flag_reaches_an_inherited_needs_expression(proj, args):
    proc = _dfm(proj, "bundle", *args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ran = _needs_run(proj)
    assert len(ran) == 1 and ran[0].endswith("holder-dbg"), ran


def test_without_the_flag_the_default_still_applies(proj):
    proc = _dfm(proj, "bundle")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ran = _needs_run(proj)
    assert len(ran) == 1 and ran[0].endswith("holder-opt"), ran


@pytest.mark.parametrize("args,level", [
    (["--variant", "dbg"], "dbg"),
    (["-D", "variant=dbg"], "dbg"),
    ([], "opt"),
])
def test_a_flag_reaches_another_registered_package(proj, args, level):
    proc = _dfm(proj, "req", *args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    path = proj / "leaf" / "rundir" / "leaf.req" / "leaf.req.exec_data.json"
    with open(path) as fp:
        items = json.load(fp)["output"]["output"]
    assert [i["level"] for i in items] == [level], items
