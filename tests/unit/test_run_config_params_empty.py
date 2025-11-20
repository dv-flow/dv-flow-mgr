import textwrap, os
from dv_flow.mgr.cmds.cmd_run import CmdRun

class Args:
    def __init__(self, root, tasks):
        self.tasks = tasks
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root

def test_run_config_with_empty_params(tmp_path, capsys):
    # Base package
    (tmp_path / 'pkg1.yaml').write_text(textwrap.dedent('''\
    package:
      name: pkg1
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: Hello pkg1.t1
      - name: t2
        uses: std.Message
        needs: [t1]
        with:
          msg: Hello pkg1.t2
    '''))
    # Root with a config that doesn't specify params (empty list case triggers previous bug)
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: root
      uses: pkg1
      imports:
      - pkg1.yaml
      tasks: []
      configs:
      - name: default
        tasks:
        - override: t1
          uses: std.Message
          with:
            msg: Hello root::default::t1
    '''))
    args = Args(str(tmp_path), ['t2'])
    # Expect failure prior to fix: override target resolution error should NOT occur now
    CmdRun()(args)
    out = capsys.readouterr().out
    assert 'override target task' not in out
    assert 'root.t1: Hello root::default::t1' in out
    assert 'root.t2: Hello pkg1.t2' in out
