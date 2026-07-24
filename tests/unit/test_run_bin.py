import json
import os
import stat
import subprocess
from dv_flow.mgr.out import install_run_bin


def test_install_run_bin_creates_executables(tmpdir):
    rundir = str(tmpdir)
    bindir = install_run_bin(rundir)
    assert bindir == os.path.join(rundir, "bin")
    for name in ("dfm-out", "dfm"):
        p = os.path.join(bindir, name)
        assert os.path.isfile(p)
        assert os.stat(p).st_mode & stat.S_IXUSR
        assert p  # executable shim present


def test_install_run_bin_idempotent(tmpdir):
    rundir = str(tmpdir)
    bindir = install_run_bin(rundir)
    shim = os.path.join(bindir, "dfm-out")
    mtime = os.path.getmtime(shim)
    # A second call with unchanged content must not rewrite the file.
    install_run_bin(rundir)
    assert os.path.getmtime(shim) == mtime


def test_run_bin_shim_functional(tmpdir):
    rundir = str(tmpdir)
    bindir = install_run_bin(rundir)
    outfile = os.path.join(rundir, "out.jsonl")
    env = os.environ.copy()
    env["DFM_OUTPUT"] = outfile
    # Invoke the shim (not the entry-point script) directly.
    r = subprocess.run(
        [os.path.join(bindir, "dfm-out"), "fileset", "--filetype", "x", "a.txt"],
        env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    item = json.loads(open(outfile).read().strip())
    assert item["type"] == "std.FileSet"
    assert item["filetype"] == "x"
    assert item["files"] == ["a.txt"]
