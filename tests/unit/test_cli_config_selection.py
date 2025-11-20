import sys, subprocess, os

def test_cli_config_selection_default(tmp_path):
    # Create a minimal project with a default config that overrides t1
    (tmp_path / 'pkg1.yaml').write_text('''\
package:
  name: pkg1
  tasks:
  - name: t1
    uses: std.Message
    with:
      msg: base t1
  - name: t2
    uses: std.Message
    needs: [t1]
    with:
      msg: base t2
''')
    (tmp_path / 'flow.yaml').write_text('''\
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
        msg: cfg t1
''')

    cmd = [sys.executable, '-m', 'dv_flow.mgr', 'run', '-c', 'default', 't2']
    proc = subprocess.run(cmd, cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, f"dfm run -c default t2 failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    # Expect overridden message for t1 and base message for t2
    assert 'root.t1: cfg t1' in proc.stdout
    assert 'root.t2: base t2' in proc.stdout
