#****************************************************************************
#* lineage.py -- type lineage of a Result node
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
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
"""``type_lineage`` for Result nodes: the ``uses:`` chain from the type
registry (the same walk ``type_match.is_a`` uses), cut at ``std.Result``."""
from ..type_match import type_lineage as _type_lineage

RESULT_TYPE = "std.Result"


def type_lineage(type_name, resolve=None):
    """``["hdlsim.TestResult", "std.TestResult", "std.Result"]``.

    The chain stops at ``std.Result`` (``std.DataItem`` is not part of a
    node's identity). A type that does not resolve gets ``std.Result``
    appended, since it was found inside a Result tree.
    """
    chain = _type_lineage(type_name or RESULT_TYPE, resolve)
    if RESULT_TYPE in chain:
        return chain[:chain.index(RESULT_TYPE) + 1]
    return chain + [RESULT_TYPE]


def is_result_type(type_name, resolve=None) -> bool:
    return RESULT_TYPE in _type_lineage(type_name, resolve) if type_name else False
