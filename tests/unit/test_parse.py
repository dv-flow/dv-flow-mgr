import io
import pytest
import yaml

from dv_flow.mgr.type_def import TypeDef

def test_typedef_1():
    flow_dv = """
package:
  name: abc
  types:
  - name: T1
    with:
    - name: F1
      doc: "Field 1"
      type: str
    - name: F2
      type:
        list:
          item: str
    - name: F3
      type:
        map:
          key: str
          item:
            list:
              item: str
"""

    data = yaml.load(io.StringIO(flow_dv), yaml.FullLoader)

    typedef = data["package"]["types"][0]
    td = TypeDef(**typedef)

    print("td=" + str(td))



