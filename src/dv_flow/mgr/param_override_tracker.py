#****************************************************************************
#* param_override_tracker.py
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
import dataclasses as dc
from typing import Dict, List, Set, Tuple


@dc.dataclass
class OverrideBindingTracker(object):
    """Records where each `-D name=value` key actually bound.

    A `-D` key is offered to several independent consumers -- package variables,
    task params keyed by task name, and task params keyed by a bare param name --
    and each silently ignores a key it does not recognize. That is deliberate: a
    bare `-D seed=42` is *meant* to miss the tasks that have no `seed`. But it
    also means a typo'd key binds nowhere and the run proceeds as though the user
    had said nothing at all.

    Consumers call `note_package_bind` / `note_task_bind` as they bind. The CLI
    then reports:

      * keys that bound nowhere (a typo, or a task that never entered the graph);
      * keys that bound in more than one namespace, which is genuinely ambiguous
        and where the qualified form (`-D pkg.key=` / `-D task.key=`) is meant.

    Only keys supplied via `-D` are tracked. `-P` param-file entries reach the
    same consumers but are not command-line keys, so a bind reported for a key
    that was never registered is ignored.
    """

    # Raw keys as typed on the command line, in order.
    keys : List[str] = dc.field(default_factory=list)
    _package_binds : Dict[str, Set[str]] = dc.field(default_factory=dict)
    _task_binds : Dict[str, Set[str]] = dc.field(default_factory=dict)

    def note_package_bind(self, key : str, pkg_name : str):
        """Record that `key` bound a variable of package `pkg_name`."""
        if key in self.keys:
            self._package_binds.setdefault(key, set()).add(pkg_name)

    def note_task_bind(self, key : str, task_name : str):
        """Record that `key` bound a parameter of task `task_name`."""
        if key in self.keys:
            self._task_binds.setdefault(key, set()).add(task_name)

    def unmatched(self) -> List[str]:
        """Keys that bound nowhere, in command-line order."""
        return [k for k in self.keys
                if k not in self._package_binds and k not in self._task_binds]

    def ambiguous(self) -> List[Tuple[str, List[str], List[str]]]:
        """Keys that bound both a package variable and a task parameter.

        Returns (key, package names, task names) triples in command-line order.
        """
        ret = []
        for k in self.keys:
            if k in self._package_binds and k in self._task_binds:
                ret.append((k,
                            sorted(self._package_binds[k]),
                            sorted(self._task_binds[k])))
        return ret

    def warnings(self) -> List[str]:
        """Human-readable diagnostics, ready to print. Empty when all keys bound
        exactly one way."""
        ret = []
        for key in self.unmatched():
            ret.append(
                "-D %s matched no package variable or task parameter. "
                "Check the spelling, or use 'dfm show task <name>' to list a "
                "task's parameters." % key)
        for key, pkgs, tasks in self.ambiguous():
            msg = ("-D %s is ambiguous: it bound package variable(s) on %s and "
                   "task parameter(s) on %s." % (
                       key, ", ".join(pkgs), ", ".join(tasks)))
            if "." not in key:
                # A bare key can be qualified. A dotted key already carries its
                # qualifier -- `a.b` is *both* package `a` var `b` and task `a`
                # param `b` -- so there is no more-specific form to suggest.
                msg += (" Qualify it as '-D %s.%s=...' or '-D %s.%s=...' to "
                        "select one." % (pkgs[0], key, tasks[0], key))
            ret.append(msg)
        return ret
