import enum
import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node import TaskNode
from .task_params_ctor import TaskParamsCtor
from .param_ref_eval import ParamRefEval
from .param import Param

@dc.dataclass
class TaskNodeLeaf(TaskNode):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult'] = dc.field(default=None)

    async def do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        self._log.debug("--> do_run: %s" % self.name)
        changed = False
        for dep,_ in self.needs:
            changed |= dep.changed

        self.rundir = rundir

        # TODO: Form dep-map from inputs

        dep_m = {}
        for need,block in self.needs:
            self._log.debug("dep %s dep_m: %s" % (need.name, str(dep_m)))
            if not block:
                for subdep in need.output.dep_m.keys():
                    if subdep not in dep_m.keys():
                        dep_m[subdep] = []
                    for dep in need.output.dep_m[subdep]:
                        if dep not in dep_m[subdep]:
                            dep_m[subdep].append(dep)
        self._log.debug("input dep_m: %s %s" % (self.name, str(dep_m)))

        sorted = toposort.toposort(dep_m)

        in_params_m = {}
        added_srcs = set()
        for need,block in self.needs:
            self._log.debug("Process need=%s block=%s" % (need.name, block))
            if not block:
                for p in need.output.output:

                    # Avoid adding parameters from a single task more than once
                    key = (p.src, p.seq)
                    if key not in added_srcs:
                        added_srcs.add(key)
                        if p.src not in in_params_m.keys():
                            in_params_m[p.src] = []
                        in_params_m[p.src].append(p)

        # in_params holds parameter sets ordered by dependency
        in_params = []
        for sorted_s in sorted:
            self._log.debug("sorted_s: %s" % str(sorted_s))
            for dep in sorted_s:
                if dep in in_params_m.keys():
                    self._log.debug("(%s) Extend with: %s" % (dep, str(in_params_m[dep])))
                    in_params.extend(in_params_m[dep])

        self._log.debug("in_params[1]: %s" % ",".join(p.src for p in in_params))

        # Create an evaluator for substituting param values
        eval = ParamRefEval()

        self._log.debug("in_params[2]: %s" % ",".join(p.src for p in in_params))
        eval.setVar("in", in_params)
        eval.setVar("rundir", rundir)

        # Set variables from the inputs
        for need in self.needs:
            for name,value in {"rundir" : need[0].rundir}.items():
                eval.setVar("%s.%s" % (need[0].name, name), value)

        # Default inputs is the list of parameter sets that match 'consumes'
        inputs = []
        if self.consumes is not None and len(self.consumes):
            for in_p in in_params:
                if self._matches(in_p, self.consumes):
                    inputs.append(in_p)

        for name,field in self.params.model_fields.items():
            value = getattr(self.params, name)
            if type(value) == str:
                if value.find("${{") != -1:
                    new_val = eval.eval(value)
                    self._log.debug("Param %s: Evaluate expression \"%s\" => \"%s\"" % (name, value, new_val))
                    setattr(self.params, name, new_val)
            elif isinstance(value, list):
                for i,elem in enumerate(value):
                    if elem.find("${{") != -1:
                        new_val = eval.eval(elem)
                        value[i] = new_val

        input = TaskDataInput(
            name=self.name,
            changed=changed,
            srcdir=self.srcdir,
            rundir=rundir,
            params=self.params,
            inputs=inputs,
            memento=memento)

        self._log.debug("--> Call task method %s" % str(self.task))
        self.result : TaskDataResult = await self.task(self, input)
        self._log.debug("<-- Call task method %s" % str(self.task))

        output=self.result.output.copy()
        for i,out in enumerate(output):
            out.src = self.name
            out.seq = i

        self._log.debug("output[1]: %s" % str(output))

        # Pass-through all dependencies
        # Add an entry for ourselves
        dep_m[self.name] = list(need.name for need,_ in self.needs)

        if self.passthrough:
            self._log.debug("passthrough: %s" % self.name)

            if self.consumes is None or len(self.consumes) == 0:
                self._log.debug("Propagating all input parameters to output")
                for need,block in self.needs:
                    if not block:
                        output.extend(need.output.output)
            else:
                # Filter out parameter sets that were consumed
                self._log.debug("Propagating non-consumed input parameters to output")
                self._log.debug("consumes: %s" % str(self.consumes))
                for need,block in self.needs:
                    if not block:
                        for out in need.output.output:
                            if not self._matches(out, self.consumes):
                                self._log.debug("Propagating type %s from %s" % (
                                    getattr(out, "type", "<unknown>"),
                                    getattr(out, "src", "<unknown>")))
                                output.append(out)
        else:
            self._log.debug("non-passthrough: %s (only local outputs propagated)" % self.name)
            # empty dependency map
#            dep_m = {
#                self.name : []
#            }

        self._log.debug("output dep_m: %s %s" % (self.name, str(dep_m)))
        self._log.debug("output[2]: %s" % str(output))

        # Store the result
        self.output = TaskDataOutput(
            changed=self.result.changed,
            dep_m=dep_m,
            output=output)

        # TODO: 
        self._log.debug("<-- do_run: %s" % self.name)

        return self.result

    def __hash__(self):
        return id(self)