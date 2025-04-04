
import pydantic.dataclasses as pdc
from pydantic import BaseModel

#
# - task:
#   needs: 
#   - if: abc
#       then: abc
#       else: def 
#     
class CondDef(BaseModel):
    if_then : str = pdc.Field(
        description="Condition to evaluate")
    then : str = pdc.Field(
        description="Task to execute if the condition is true")