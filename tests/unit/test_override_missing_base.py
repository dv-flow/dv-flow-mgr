import os
import textwrap
from dv_flow.mgr import PackageLoader

class MarkerCollector:
    def __init__(self):
        self.error_count = 0
        self.markers = []
    def __call__(self, marker):
        # severity 2 is error in this project
        try:
            sev = marker.severity.value if hasattr(marker.severity, 'value') else marker.severity
        except Exception:
            sev = marker.severity
        if str(sev).lower().endswith('error') or sev == 2:
            self.error_count += 1
        self.markers.append(marker)


def test_override_missing_base(tmp_path):
    # Base package with no tasks
    (tmp_path / "pkg1.yaml").write_text(textwrap.dedent(
        """
        package:
          name: pkg1
        """
    ))
    # Root package attempts to override missing task 't1'
    (tmp_path / "flow.yaml").write_text(textwrap.dedent(
        """
        package:
          name: root
          uses: pkg1
          imports:
          - pkg1.yaml
          tasks:
          - override: t1
            uses: std.Message
            with:
              msg: "Hello root::t1"
        """
    ))

    markers = MarkerCollector()
    _ = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmp_path, "flow.yaml"))
    assert markers.error_count >= 1, "Expected an error when overriding a non-existent base task"
    # Check message text for clarity
    assert any("override target task 't1' not found" in getattr(m, 'msg', str(m)) for m in markers.markers)
