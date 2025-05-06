import enum
import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult, TaskMarker, SeverityE
from .task_def import ConsumesE, PassthroughE
from .task_node import TaskNode
from .task_run_ctxt import TaskRunCtxt
from .param import Param

@dc.dataclass
class TaskNodeLeaf(TaskNode):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult'] = dc.field(default=None)

    async def do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        try:
            ret = await self._do_run(runner, rundir, memento)
        except Exception as e:
            print("Exception: %s" % str(e))
            ret = TaskDataResult()
            raise e

        return ret

    async def _do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        self._log.debug("--> do_run: %s" % self.name)
        changed = False
        for dep,_ in self.needs:
            changed |= dep.changed

        self.rundir = rundir

        if self.params is None:
            raise Exception("params is None (%s)" % str(self))

        # TODO: Form dep-map from inputs

        dep_m = {}
        for i,(need,block) in enumerate(self.needs):
            self._log.debug("dep %s dep_m: %s" % (need.name, str(dep_m)))
            if not block:
                for subdep in need.output.dep_m.keys():
                    if subdep not in dep_m.keys():
                        dep_m[subdep] = []
                    for dep in need.output.dep_m[subdep]:
                        if dep not in dep_m[subdep]:
                            dep_m[subdep].append(dep)
        self._log.debug("input dep_m: %s %s" % (self.name, str(dep_m)))

        # This gets the dependencies in topological order
#        sorted = toposort.toposort(dep_m)

        # Now, process the 'needs' in the order that they're listed
        in_params = []
        in_params_s = set()
        in_task_s = set()

        for need, _ in self.needs:
            if need not in in_task_s:
                in_task_s.add(need)
                for item in need.output.output:
                    key = (item.src, item.seq)
                    if key not in in_params_s:
                        in_params_s.add(key)
                        in_params.append(item)

        # 
        # in_params_m = {}
        # added_srcs = set()
        # for need,block in self.needs:
        #     self._log.debug("Process need=%s block=%s" % (need.name, block))
        #     if not block:
        #         for p in need.output.output:

        #             # Avoid adding parameters from a single task more than once
        #             key = (p.src, p.seq)
        #             if key not in added_srcs:
        #                 added_srcs.add(key)
        #                 if p.src not in in_params_m.keys():
        #                     in_params_m[p.src] = []
        #                 in_params_m[p.src].append(p)

        # # in_params holds parameter sets ordered by dependency
        # in_params = []
        # for sorted_s in sorted:
        #     self._log.debug("sorted_s: %s" % str(sorted_s))
        #     for dep in sorted_s:
        #         if dep in in_params_m.keys():
        #             self._log.debug("(%s) Extend with: %s" % (dep, str(in_params_m[dep])))
        #             in_params.extend(in_params_m[dep])

        self._log.debug("in_params[1]: %s" % ",".join(p.src for p in in_params))



        # Default inputs is the list of parameter sets that match 'consumes'
        inputs = []
        if isinstance(self.consumes, list) and len(self.consumes):
            self._log.debug("consumes(list): %s" % str(self.consumes))
            for in_p in in_params:
                if self._matches(in_p, self.consumes):
                    inputs.append(in_p)
        elif self.consumes == ConsumesE.All:
            inputs = in_params.copy()
            self._log.debug("consumes(all): %s" % str(self.consumes))
        else:
            self._log.debug("consumes(unknown): %s" % str(self.consumes))

        input = TaskDataInput(
            name=self.name,
            changed=changed,
            srcdir=self.srcdir,
            rundir=rundir,
            params=self.params,
            inputs=inputs,
            memento=memento)
        
        ctxt = TaskRunCtxt(
            runner=runner, 
            ctxt=self.ctxt,
            rundir=input.rundir)

        self._log.debug("--> Call task method %s" % str(self.task))
        try:
            self.result : TaskDataResult = await self.task(ctxt, input)
        except Exception as e:
            print("== Task threw exception ==")
            self._log.error("Task %s failed: %s" % (self.name, str(e)))
            self._log.exception(e)
            self.result = TaskDataResult(
                status=1,
                changed=False,
                output=[],
                markers=[
                    TaskMarker(
                        msg="Task implementation raised an exception: %s" % str(e),
                        severity=SeverityE.Error
                    )
                ],
                memento=None)
        self._log.debug("<-- Call task method %s" % str(self.task))

        self.result.markers.extend(ctxt._markers)

        output = []

        self._log.debug("output[1]: %s" % str(output))

        # Pass-through all dependencies
        # Add an entry for ourselves
        dep_m[self.name] = list(need.name for need,_ in self.needs)

        if isinstance(self.passthrough, list):
            self._log.warning("List-based passthrough not yet supported")
        elif self.passthrough == PassthroughE.All:
            self._log.debug("Propagating all input parameters to output")
            for need,block in self.needs:
                if not block:
                    output.extend(need.output.output)
        elif self.passthrough == PassthroughE.Unused:
            self._log.debug("passthrough: %s" % self.name)

            if self.consumes == ConsumesE.No or (isinstance(self.consumes, list) and len(self.consumes) == 0):
                self._log.debug("Propagating all input parameters to output")
                for need,block in self.needs:
                    if not block:
                        output.extend(need.output.output)
            elif self.consumes == ConsumesE.All:
                self._log.debug("All inputs are consumed, so not propagating any")
            elif isinstance(self.consumes, list):
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
            self._log.debug("non-passthrough: %s (only local outputs propagated) %s" % (
                self.name,
                str(self.passthrough)))
            # empty dependency map
#            dep_m = {
#                self.name : []
#            }

        # Add our own output
        local_out = self.result.output.copy()
        for i,out in enumerate(local_out):
            out.src = self.name
            out.seq = i
            output.append(out)

        self._log.debug("output dep_m: %s %s" % (self.name, str(dep_m)))
        self._log.debug("output[2]: %s" % str(output))

        # Store the result
        self.output = TaskDataOutput(
            changed=self.result.changed,
            dep_m=dep_m,
            output=output)
        
        if self.save_exec_data:
            self._save_exec_data(rundir, ctxt, input)

        # TODO: 
        self._log.debug("<-- do_run: %s" % self.name)

        if self.result is None:
            raise Exception("Task %s did not produce a result" % self.name)

        if self.output is None:
            raise Exception("Task %s did not produce a result" % self.name)
        return self.result
    
    def _processNeed(self, need, in_params, in_task_s):
        # Go depth-first
        for nn, _ in need.needs:
            self._processNeed(nn, in_params, in_task_s)

        if need not in in_task_s:
            in_params.extend(need.output.output)
        



    def __hash__(self):
        return id(self)
