#****************************************************************************
#* test_ctxt_cores.py
#*
#* `ctxt.cores` -- how many CPU cores a task may use.
#*
#* A task that shells out to something with a parallelism flag must pass this
#* down rather than asking the machine how many CPUs it has. Under a scheduler
#* the machine's answer is the NODE's core count, not this job's allocation, and
#* using it oversubscribes the node -- which is how a bare `make -j` gets
#* cc1plus killed by the OOM killer.
#****************************************************************************
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr.task_run_ctxt import TaskRunCtxt


class _Runner:
    def __init__(self, nproc=None):
        if nproc is not None:
            self.nproc = nproc


def _ctxt(env=None, nproc=None):
    c = TaskRunCtxt(runner=_Runner(nproc), ctxt=None, rundir="/tmp")
    c._env = env or {}
    return c


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("DFM_CORES", "LSB_DJOB_NUMPROC", "LSB_MCPU_HOSTS",
                "SLURM_CPUS_PER_TASK", "SLURM_CPUS_ON_NODE", "NSLOTS"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------

def test_falls_back_to_the_runner_budget(monkeypatch):
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=7), ctxt=None, rundir="/tmp")
    assert c.cores == 7


def test_falls_back_to_the_cpu_count(monkeypatch):
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(), ctxt=None, rundir="/tmp")
    assert c.cores == (os.cpu_count() or 1)


def test_an_lsf_allocation_wins_over_the_local_budget(monkeypatch):
    """Deliberately the ALLOCATION, not the request: they can differ, and only
    one of them is true."""
    monkeypatch.setenv("LSB_DJOB_NUMPROC", "3")
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=64), ctxt=None, rundir="/tmp")
    assert c.cores == 3


def test_an_explicit_override_wins_over_everything(monkeypatch):
    monkeypatch.setenv("LSB_DJOB_NUMPROC", "3")
    monkeypatch.setenv("DFM_CORES", "5")
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=64), ctxt=None, rundir="/tmp")
    assert c.cores == 5


def test_the_lsf_host_slot_list_is_summed(monkeypatch):
    """LSF also publishes the allocation as 'host slots host slots ...'."""
    monkeypatch.setenv("LSB_MCPU_HOSTS", "hostA 2 hostB 4")
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=64), ctxt=None, rundir="/tmp")
    assert c.cores == 6


def test_a_slurm_allocation_is_honored(monkeypatch):
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "8")
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=64), ctxt=None, rundir="/tmp")
    assert c.cores == 8


def test_a_junk_value_does_not_break_resolution(monkeypatch):
    """A malformed allocation must fall through, not crash the task."""
    monkeypatch.setenv("LSB_DJOB_NUMPROC", "not-a-number")
    from dv_flow.mgr import task_run_ctxt as m
    c = m.TaskRunCtxt(runner=_Runner(nproc=9), ctxt=None, rundir="/tmp")
    assert c.cores == 9


# ---------------------------------------------------------------------------
# It reaches the child
# ---------------------------------------------------------------------------

def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


SHOW = '''\
package:
    name: p
    tasks:
    - root: show
      shell: bash
      run: echo "cores=$DFM_CORES"
'''


def test_dfm_cores_reaches_a_shell_body(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(SHOW))
    proc = _dfm(tmp_path, "show", "-j", "4")
    assert proc.returncode == 0, proc.stderr
    log = (tmp_path / "rundir" / "p.show").glob("*.log")
    text = "".join(p.read_text() for p in log)
    assert "cores=4" in text


def test_a_batch_allocation_reaches_a_shell_body(tmp_path, monkeypatch):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(SHOW))
    env = dict(os.environ, LSB_DJOB_NUMPROC="2")
    proc = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run", "show", "-j", "16"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    text = "".join(p.read_text()
                   for p in (tmp_path / "rundir" / "p.show").glob("*.log"))
    assert "cores=2" in text


def test_the_shared_context_env_is_not_mutated(tmp_path):
    """`env` defaults to the shared context environment; adding DFM_CORES to it
    in place would leak the value into every later task."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - {name: a, shell: bash, run: 'echo a=$DFM_CORES'}
        - {root: b, shell: bash, needs: [a], run: 'echo b=$DFM_CORES'}
    '''))
    proc = _dfm(tmp_path, "b", "-j", "3")
    assert proc.returncode == 0, proc.stderr
