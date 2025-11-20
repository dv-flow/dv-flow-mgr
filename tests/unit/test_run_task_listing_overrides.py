import os, textwrap, io, sys
from dv_flow.mgr.cmds.cmd_run import CmdRun
from dv_flow.mgr import PackageLoader

class Args:  # minimal args holder
    def __init__(self, root):
        self.tasks = []
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root

# Utility: emulate get_rootdir(args) returning cwd or specified root
from dv_flow.mgr.cmds.util import get_rootdir

def test_run_list_overrides(tmp_path, capsys):
    # Base package with two tasks (t1, t2)
    (tmp_path / 'pkg1.yaml').write_text(textwrap.dedent('''\
    package:
      name: pkg1
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: pkg1.t1
      - name: t2
        uses: std.Message
        with:
          msg: pkg1.t2
    '''))
    # Root overrides only t1
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: root
      uses: pkg1
      imports:
      - pkg1.yaml
      tasks:
      - override: t1
        uses: std.Message
        with:
          msg: root.t1
    '''))
    # Invoke CmdRun with no task specified to list tasks
    args = Args(root=str(tmp_path))
    # Monkeypatch get_rootdir if needed (Args passes directory); util expects path
    # Run command
    CmdRun()(args)
    out = capsys.readouterr().out
    # Expect only root.t1 (override); non-root tasks should not be listed
    assert 'root.t1' in out
    assert 'pkg1.t2' not in out
    assert 'pkg1.t1' not in out
