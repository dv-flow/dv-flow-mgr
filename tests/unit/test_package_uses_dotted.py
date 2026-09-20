#****************************************************************************
#* test_package_uses_dotted.py
#*
#* Package `uses:` where the base has a DOTTED name, and where the chain is
#* more than one rung deep.
#*
#* Both are what a library of project archetypes looks like: the archetypes are
#* named for what they are (`project.dv`, `project.dv.uvm`), and the specific
#* one inherits the general one, so a project inheriting `project.dv.uvm` sits
#* at the end of a three-package chain.
#****************************************************************************
import subprocess
import sys
import textwrap


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


def _write(d, **files):
    for name, text in files.items():
        (d / name.replace("_", ".")).write_text(textwrap.dedent(text))
    return d


def test_a_dotted_base_name_is_not_read_as_a_task_namespace(tmp_path):
    """A package name may contain dots. Computing an inherited task's short name
    by splitting off the FIRST dotted component read the rest of the base's own
    name as a task namespace -- inheriting `a.b.greet` produced `leaf.b.greet`,
    so the task a reader asked for by its short name did not exist."""
    _write(
        tmp_path,
        base_dv='''\
        package:
            name: a.b
            tasks:
            - root: greet
              uses: std.Message
              with: {msg: "hello from the base"}
        ''',
        flow_dv='''\
        package:
            name: leaf
            uses: a.b
            imports:
            - base.dv
        ''')
    proc = _dfm(tmp_path, "greet")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "hello from the base" in proc.stdout
    # The inherited task is the LEAF's, under its own name.
    assert "leaf.greet" in proc.stdout
    assert "leaf.b.greet" not in proc.stdout


def test_an_override_reaches_a_task_inherited_from_a_dotted_base(tmp_path):
    """The consequence of the mis-named alias: `override:` looks the target up
    by `<base>.<target>`, which the mis-naming had put somewhere else. The whole
    point of an archetype is that a project fills in its slots, so this is the
    failure that made a dotted archetype name unusable."""
    _write(
        tmp_path,
        base_dv='''\
        package:
            name: a.b
            tasks:
            - root: slot
              uses: std.Message
              with: {msg: "unimplemented"}
        ''',
        flow_dv='''\
        package:
            name: leaf
            uses: a.b
            imports:
            - base.dv
            tasks:
            - override: slot
              with: {msg: "implemented by the leaf"}
        ''')
    proc = _dfm(tmp_path, "slot")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "implemented by the leaf" in proc.stdout


def test_a_task_inherited_through_two_packages_keeps_its_parameters(tmp_path):
    """An inherited task is aliased with neither `param_defs` nor `paramT` of
    its own -- it gets them from the chain. A two-rung chain therefore puts an
    EMPTY rung between the task and the declarations, and a one-rung look-ahead
    concluded the task had no parameters at all.

    Read through the builder rather than through a run, because that is the path
    an `elaborate:` clause uses: hdlsim's backend selection reads `sim` this way
    and cannot tell "no params" from "sim not set" -- it reports the latter."""
    from dv_flow.mgr.util import loadProjPkgDef
    from dv_flow.mgr.task_graph_builder import TaskGraphBuilder

    _write(
        tmp_path,
        base_dv='''\
        package:
            name: base
            tasks:
            - name: holder
              uses: std.Message
              with:
                knob: {type: str, value: "from-the-base"}
                msg: "x"
        ''',
        mid_dv='''\
        package:
            name: mid
            uses: base
            imports:
            - base.dv
        ''',
        flow_dv='''\
        package:
            name: leaf
            uses: mid
            imports:
            - mid.dv
        ''')

    loader, pkg = loadProjPkgDef(str(tmp_path))
    builder = TaskGraphBuilder(pkg, str(tmp_path / "rundir"), loader=loader)

    params = builder._build_task_params(pkg.task_m["leaf.holder"])
    assert params is not None, "two-rung inheritance lost the task's parameters"
    assert params.knob == "from-the-base"


def test_a_package_variable_survives_two_rungs_of_inheritance(tmp_path):
    """The value side of the same chain: an inherited task's parameter default
    referring to a package variable resolves against the variable the LEAF ends
    up with, wherever along the chain either was declared."""
    _write(
        tmp_path,
        base_dv='''\
        package:
            name: base
            with:
              knob: {type: str, value: base-value}
            tasks:
            - root: show
              uses: std.Message
              with: {msg: "knob=${{ knob }}"}
        ''',
        mid_dv='''\
        package:
            name: mid
            uses: base
            imports:
            - base.dv
        ''',
        flow_dv='''\
        package:
            name: leaf
            uses: mid
            imports:
            - mid.dv
            with:
              knob: leaf-value
        ''')
    proc = _dfm(tmp_path, "show")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "knob=leaf-value" in proc.stdout
