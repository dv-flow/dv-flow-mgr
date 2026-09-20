#****************************************************************************
#* not_provided.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""`std.NotProvided` -- a project declaring that a slot does not apply to it.

An archetype declares a slot; a project either fills it in or says it has no
such flow. Saying so has to be a real answer, with three properties:

  * it does not appear in `dfm run`, because the project does not offer that
    verb and listing it would be an invitation to type something that cannot
    work;
  * typing it anyway says *that*, rather than silently succeeding -- silent
    success on an unfilled slot is the failure `requires:` exists to prevent,
    and an escape hatch that reintroduces it is worse than none; and
  * it satisfies `std.check.Implemented`, because a declared not-provided slot
    is answered, not neglected.

Nothing else expresses all three. `severity: off` silences the check and
leaves a task that reports success; `iff: false` leaves it listed and silently
does nothing; dropping `root` scope hides it but still fails with a diagnostic
about being unimplemented, which is the wrong reason.
"""

from ..task_data import TaskDataResult, TaskMarker, SeverityE
from ..task import iter_uses_chain

#: Full name of the marker task. Membership is tested along the `uses:` chain,
#: so a project may derive its own not-provided base (with a house-style
#: message, say) and still be recognized.
NOT_PROVIDED = "std.NotProvided"


def is_not_provided(task) -> bool:
    """Whether `task` is declared not-provided.

    The `uses:` chain rather than the immediate type, for the same reason every
    other chain question is asked that way: a project's `override:` of a slot
    gets its implementation from what it uses, and an intermediate archetype may
    have declined a slot on behalf of the projects that inherit it.
    """
    return any(getattr(t, 'name', None) == NOT_PROVIDED
               for t in iter_uses_chain(task))


async def NotProvided(runner, input) -> TaskDataResult:
    leaf = input.name.rsplit('.', 1)[-1] if '.' in input.name else input.name
    return TaskDataResult(
        status=1,
        markers=[TaskMarker(
            severity=SeverityE.Error,
            msg=("this project does not provide '%s'. It is declared "
                 "not-provided here, so there is nothing to run." % leaf))])
