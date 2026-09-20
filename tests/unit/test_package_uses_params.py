#****************************************************************************
#* test_package_uses_params.py
#*
#* Package `uses:` inheritance of package VARIABLES.
#*
#* `uses:` already inherited a base package's tasks and types, and
#* `collect_package_cli` already collected its `cli:` flags along the same
#* chain. The variables those flags set were the piece that did not come with
#* them, which made a base project able to declare `--sim` but not to declare
#* the `sim` its leaves (and its own inherited tasks) read.
#*
#* The ordering these tests pin: the base package is reached through the
#* IMPORTS, so a package's parameter type cannot be final until they are
#* loaded. The provisional build that precedes them must not report the
#* diagnostics of a half-built picture -- see `_getParamT(report_errors=...)`.
#****************************************************************************
import subprocess
import sys
import textwrap

import pytest


BASE = '''\
package:
    name: base
    with:
      sim:
        type: str
        value: vlt
        desc: Simulator backend
        values: [vlt, mti, vcs]
      trace:
        type: bool
        value: false
    tasks:
    - root: base-show
      uses: std.Message
      with: {msg: "base sees sim=${{ sim }} trace=${{ trace }}"}
'''


def _write(d, leaf, base=BASE):
    (d / "base.dv").write_text(textwrap.dedent(base))
    (d / "flow.dv").write_text(textwrap.dedent(leaf))
    return d


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


LEAF = '''\
package:
    name: leaf
    uses: base
    imports:
    - base.dv
    tasks:
    - root: leaf-show
      uses: std.Message
      with: {msg: "leaf sees sim=${{ sim }} trace=${{ trace }}"}
'''


def test_a_leaf_reads_a_base_package_variable(tmp_path):
    """The whole point: a base project declares the project-wide knobs and the
    leaves use them by name, without restating the declaration."""
    proc = _dfm(_write(tmp_path, LEAF), "leaf-show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "leaf sees sim=vlt trace=false" in proc.stdout


def test_an_inherited_task_reads_the_base_variable(tmp_path):
    """A base task is elaborated in the LEAF's package context, so without
    inherited variables the base could not use its own knobs -- a failure its
    author cannot work around from the leaf."""
    proc = _dfm(_write(tmp_path, LEAF), "base-show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "base sees sim=vlt" in proc.stdout


def test_a_leaf_overrides_an_inherited_value_without_restating_its_type(tmp_path):
    """The value-only form is how every other `uses:` override reads. It is
    also the case the provisional build gets wrong -- `sim` is not a field
    until the base is in scope -- so it doubles as the regression test for
    holding those diagnostics back."""
    proc = _dfm(_write(tmp_path, '''\
    package:
        name: leaf
        uses: base
        imports:
        - base.dv
        with:
          sim: mti
        tasks:
        - root: leaf-show
          uses: std.Message
          with: {msg: "leaf sees sim=${{ sim }}"}
    '''), "leaf-show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "leaf sees sim=mti" in proc.stdout
    assert "Field sim not found" not in proc.stdout


def test_a_leaf_redeclaration_wins_over_the_base_default(tmp_path):
    proc = _dfm(_write(tmp_path, '''\
    package:
        name: leaf
        uses: base
        imports:
        - base.dv
        with:
          sim: {type: str, value: vcs}
        tasks:
        - root: leaf-show
          uses: std.Message
          with: {msg: "leaf sees sim=${{ sim }}"}
    '''), "leaf-show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "leaf sees sim=vcs" in proc.stdout


def test_a_define_reaches_an_inherited_variable(tmp_path):
    proc = _dfm(_write(tmp_path, LEAF), "leaf-show", "-D", "sim=mti")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "leaf sees sim=mti" in proc.stdout


def test_an_inherited_bool_keeps_its_type(tmp_path):
    """Type, not just name. The CLI layer reads the type off the package's
    parameter model to decide that `--trace` is a switch rather than an option
    taking a value; before the variable was inherited there was nothing there
    to read and a base-declared bool silently demanded an argument."""
    base_cli = BASE.replace("        value: false",
                            "        value: false\n        cli: true")
    proc = _dfm(_write(tmp_path, LEAF, base=base_cli), "leaf-show", "--trace")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "trace=true" in proc.stdout


def test_a_value_set_on_an_inherited_variable_is_enforced(tmp_path):
    """The declaration lives in the base's package definition, so checking only
    the leaf's would skip exactly the variables a base project exists to
    declare."""
    proc = _dfm(_write(tmp_path, LEAF), "leaf-show", "-D", "sim=bogus")
    assert proc.returncode != 0
    assert "is not a valid value" in proc.stdout


def test_inheritance_is_transitive(tmp_path):
    """Each package inherits from the one it `uses:`, and a base was itself
    built that way -- so a three-level chain needs no separate walk."""
    (tmp_path / "root.dv").write_text(textwrap.dedent('''\
    package:
        name: rootpkg
        with:
          site: {type: str, value: hq}
    '''))
    proc = _dfm(_write(tmp_path, '''\
    package:
        name: leaf
        uses: base
        imports:
        - base.dv
        tasks:
        - root: leaf-show
          uses: std.Message
          with: {msg: "leaf sees ${{ site }}/${{ sim }}"}
    ''', base='''\
    package:
        name: base
        uses: rootpkg
        imports:
        - root.dv
        with:
          sim: {type: str, value: vlt}
    '''), "leaf-show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "leaf sees hq/vlt" in proc.stdout


def test_a_selected_config_does_not_discard_a_define(tmp_path):
    """Selecting a config rebuilds the package parameter type, and a fresh type
    has the DECLARED defaults again. The CLI is the precedence ceiling (§R2.4),
    so the overrides are re-applied to each build -- without that, `-c` silently
    inverted the ladder and `-D` lost."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          v: {type: str, value: declared}
        configs:
        - name: c
        tasks:
        - {root: t, uses: std.Message, with: {msg: "v=${{ v }}"}}
    '''))
    proc = _dfm(tmp_path, "-c", "c", "t", "-D", "v=FROMCLI")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "v=FROMCLI" in proc.stdout


def test_an_undefined_reference_is_still_reported(tmp_path):
    """Holding back the provisional build's diagnostics must not swallow a real
    one: the authoritative build reports it."""
    proc = _dfm(_write(tmp_path, '''\
    package:
        name: leaf
        uses: base
        imports:
        - base.dv
        with:
          nosuch: nope
        tasks:
        - root: leaf-show
          uses: std.Message
          with: {msg: hi}
    '''), "leaf-show")
    assert proc.returncode != 0
    assert "nosuch" in proc.stdout
