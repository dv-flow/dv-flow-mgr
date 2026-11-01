#****************************************************************************
#* __init__.py -- run results (std.Result) support
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
"""Run results: the ``std.Result`` data-item format and its run record.

* ``model``    -- pydantic models of ``results.json`` (``dvflow-results/1``)
* ``status``   -- the status vocabulary and its ordering
* ``convert``  -- data item -> ``ResultNode``
* ``api``      -- helpers for task authors (``mk_result``, ``check``, ``finish`` ...)
"""
