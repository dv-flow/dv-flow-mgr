import enum
import json
import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple, Union
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult, TaskMarker, SeverityE
from .task_def import ConsumesE, PassthroughE
from .task_node import TaskNode
from .task_run_ctxt import TaskRunCtxt
from .param import Param
from . import cache_util

@dc.dataclass
class TaskNodeLeaf(TaskNode):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult'] = dc.field(default=None)
    uptodate : Union[bool, str, None] = dc.field(default=None)
    taskdef : Any = dc.field(default=None)

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
            changed |= dep.output.changed

        self.rundir = rundir

        if self.params is None:
            raise Exception("params is None (%s)" % str(self))

        # TODO: Form dep-map from inputs

        dep_m = {}
        for i,(need,block) in enumerate(self.needs):
            self._log.debug("dep %s dep_m: %s" % (need.name, str(dep_m)))
            if not block:
                if need.output is None:
                    raise Exception("Need %s has no output (in %s)" % (
                        need.name,
                        self.name))
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
        in_params = await self.get_in_params(rundir)


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
        # std.Env items are always consumed regardless of consumes setting
        inputs = []
        if isinstance(self.consumes, list) and len(self.consumes):
            self._log.debug("consumes(list): %s" % str(self.consumes))
            for in_p in in_params:
                if self._matches(in_p, self.consumes) or getattr(in_p, "type", None) == "std.Env":
                    inputs.append(in_p)
        elif self.consumes == ConsumesE.All:
            inputs = in_params.copy()
            self._log.debug("consumes(all): %s" % str(self.consumes))
        else:
            self._log.debug("consumes(unknown): %s" % str(self.consumes))
            # Even when consumes is empty/unknown, still consume std.Env items
            for in_p in in_params:
                if getattr(in_p, "type", None) == "std.Env":
                    inputs.append(in_p)

        # Check cache first (before uptodate check)
        # Skip cache if uptodate is explicitly False
        force_run = getattr(runner, 'force_run', False)
        if not force_run and self.uptodate is not False and hasattr(runner, 'cache_providers') and runner.cache_providers:
            try:
                cache_key = await cache_util.compute_cache_key(
                self.name,
                self.taskdef,  # Pass task definition for cache settings
                self.params,
                inputs,
                rundir,
                getattr(runner, 'hash_registry', None)
            )
            except Exception as e:
                self._log.warning(f"Error computing cache key: {e}")
                cache_key = None
            
            if cache_key:
                self._log.debug(f"Checking cache for {cache_key}")
                cache_entry = await cache_util.check_cache(cache_key, runner.cache_providers)
                
                if cache_entry:
                    self._log.info(f"Cache hit for task {self.name}")
                    runner._notify(self, "cache_hit")
                    
                    # Restore output from cache entry
                    output_template = cache_entry.output_template
                    output = []
                    dep_m = {}
                    dep_m[self.name] = list(need.name for need,_ in self.needs)
                    
                    # Handle passthrough (same as uptodate case)
                    if isinstance(self.passthrough, list):
                        pass  # Not yet supported
                    elif self.passthrough == PassthroughE.All:
                        for need,block in self.needs:
                            if not block:
                                for out in need.output.output:
                                    if getattr(out, "type", None) != "std.Env":
                                        output.append(out)
                    elif self.passthrough == PassthroughE.Unused:
                        if self.consumes == ConsumesE.No or (isinstance(self.consumes, list) and len(self.consumes) == 0):
                            for need,block in self.needs:
                                if not block:
                                    for out in need.output.output:
                                        if getattr(out, "type", None) != "std.Env":
                                            output.append(out)
                        elif isinstance(self.consumes, list):
                            for need,block in self.needs:
                                if not block:
                                    for out in need.output.output:
                                        if getattr(out, "type", None) != "std.Env" and not self._matches(out, self.consumes):
                                            output.append(out)
                    
                    # Restore local outputs from cache template
                    restoration_failed = False
                    for out_data in output_template.get('output', []):
                        if out_data.get("src") == self.name:
                            # Replace ${{ rundir }} placeholders with actual rundir
                            if 'basedir' in out_data and '${{ rundir }}' in out_data['basedir']:
                                out_data['basedir'] = out_data['basedir'].replace('${{ rundir }}', rundir)
                            
                            excluded_fields = ("type", "src", "seq", "name", "params")
                            try:
                                item = runner.mkDataItem(out_data.get("type", "std.FileSet"), **{
                                    k: v for k, v in out_data.items()
                                    if k not in excluded_fields
                                })
                                item.src = self.name
                                item.seq = out_data.get("seq", 0)
                                output.append(item)
                            except Exception as e:
                                self._log.warning(f"Failed to restore cached output item: {e}")
                                # If we can't restore, run task normally
                                restoration_failed = True
                                break
                    
                    if not restoration_failed:
                        # Successfully restored all outputs
                        # Extract artifacts if present
                        if cache_entry.artifacts_path:
                            from pathlib import Path
                            for provider in runner.cache_providers:
                                try:
                                    await provider.extract_artifacts(
                                        cache_entry,
                                        Path(rundir),
                                        use_symlinks=False
                                    )
                                    break
                                except Exception as e:
                                    self._log.warning(f"Failed to extract artifacts: {e}")
                                    continue
                        
                        self.output = TaskDataOutput(
                            changed=False,
                            dep_m=dep_m,
                            output=output
                        )
                        
                        self.result = TaskDataResult(
                            status=0,
                            changed=False,
                            output=[],
                            markers=[],
                            memento=None,
                            cache_hit=True,
                            cache_stored=False
                        )
                        
                        self._log.debug(f"<-- do_run (cache hit): {self.name}")
                        return self.result

        # Check if task is up-to-date (unless force_run is set)
        if not force_run:
            is_uptodate, exec_data = await self._check_uptodate(rundir, inputs, changed)
            # Notify listeners of up-to-date status
            runner._notify(self, "uptodate" if is_uptodate else "run")
            if is_uptodate and exec_data is not None:
                # Task is up-to-date, load previous results
                self._log.debug("Task %s is up-to-date, loading previous results" % self.name)
                
                # Restore result from exec_data
                result_data = exec_data.get("result", {})
                self.result = TaskDataResult(
                    status=result_data.get("status", 0),
                    changed=False,  # Not changed since we're up-to-date
                    output=[],
                    markers=[],
                    memento=None
                )
                
                # Restore output from exec_data
                output_data = exec_data.get("output", {})
                
                # Build output list - we need to reconstruct from passthrough + local outputs
                output = []
                dep_m = {}
                dep_m[self.name] = list(need.name for need,_ in self.needs)
                
                # Handle passthrough
                if isinstance(self.passthrough, list):
                    pass  # Not yet supported
                elif self.passthrough == PassthroughE.All:
                    for need,block in self.needs:
                        if not block:
                            for out in need.output.output:
                                if getattr(out, "type", None) != "std.Env":
                                    output.append(out)
                elif self.passthrough == PassthroughE.Unused:
                    if self.consumes == ConsumesE.No or (isinstance(self.consumes, list) and len(self.consumes) == 0):
                        for need,block in self.needs:
                            if not block:
                                for out in need.output.output:
                                    if getattr(out, "type", None) != "std.Env":
                                        output.append(out)
                    elif isinstance(self.consumes, list):
                        for need,block in self.needs:
                            if not block:
                                for out in need.output.output:
                                    if getattr(out, "type", None) != "std.Env" and not self._matches(out, self.consumes):
                                        output.append(out)
                
                # Restore local outputs from saved data using mkDataItem
                saved_output = output_data.get("output", [])
                for i, out_data in enumerate(saved_output):
                    if out_data.get("src") == self.name:
                        # This is a local output, need to reconstruct the data item
                        # Exclude fields that are set separately or may not be in the type schema
                        excluded_fields = ("type", "src", "seq", "name", "params")
                        try:
                            item = runner.mkDataItem(out_data.get("type", "std.FileSet"), **{
                                k: v for k, v in out_data.items() 
                                if k not in excluded_fields
                            })
                            item.src = self.name
                            item.seq = out_data.get("seq", i)
                            output.append(item)
                        except Exception as e:
                            self._log.warning("Failed to restore output item: %s" % e)
                            # If we can't restore, we need to re-run
                            return await self._run_task(runner, rundir, inputs, changed, memento)
                
                self.output = TaskDataOutput(
                    changed=False,
                    dep_m=dep_m,
                    output=output
                )
                
                self._log.debug("<-- do_run (up-to-date): %s" % self.name)
                return self.result
        else:
            # Force run - notify that we're running
            runner._notify(self, "run")

        # If uptodate is explicitly False, mark as changed to ensure task runs
        # and downstream tasks also re-run
        if self.uptodate is False:
            changed = True

        return await self._run_task(runner, rundir, inputs, changed, memento)

    async def _run_task(self, runner, rundir, inputs, changed, memento):
        """Actually execute the task"""
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
        dep_m = {}
        dep_m[self.name] = list(need.name for need,_ in self.needs)

        if isinstance(self.passthrough, list):
            self._log.warning("List-based passthrough not yet supported")
        elif self.passthrough == PassthroughE.All:
            self._log.debug("Propagating all input parameters to output")
            for need,block in self.needs:
                if not block:
                    # Always filter out std.Env items - they are consumed by each task
                    for out in need.output.output:
                        if getattr(out, "type", None) != "std.Env":
                            output.append(out)
        elif self.passthrough == PassthroughE.Unused:
            self._log.debug("passthrough: %s" % self.name)

            if self.consumes == ConsumesE.No or (isinstance(self.consumes, list) and len(self.consumes) == 0):
                self._log.debug("Propagating all input parameters to output")
                for need,block in self.needs:
                    if not block:
                        # Always filter out std.Env items - they are consumed by each task
                        for out in need.output.output:
                            if getattr(out, "type", None) != "std.Env":
                                output.append(out)
            elif self.consumes == ConsumesE.All:
                self._log.debug("All inputs are consumed, so not propagating any")
            elif isinstance(self.consumes, list):
                # Filter out parameter sets that were consumed
                self._log.debug("Propagating non-consumed input parameters to output")
                self._log.debug("consumes: %s" % str(self.consumes))
                for need,block in self.needs:
                    if not block:
                        for out in need.output.output:
                            # Always filter out std.Env items - they are consumed by each task
                            if getattr(out, "type", None) == "std.Env":
                                self._log.debug("Skipping std.Env type from %s" % (
                                    getattr(out, "src", "<unknown>")))
                            elif not self._matches(out, self.consumes):
                                self._log.debug("Propagating type %s from %s" % (
                                    getattr(out, "type", "<unknown>"),
                                    getattr(out, "src", "<unknown>")))
                                output.append(out)
                            else:
                                self._log.debug("Skipping consumed type %s from %s" % (
                                    getattr(out, "type", "<unknown>"),
                                    getattr(out, "src", "<unknown>")))
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
        self._log.debug("local_out of %s: %d" % (self.name, len(local_out)))
        for i,out in enumerate(local_out):
            out.src = self.name
            out.seq = i
            self._log.debug("Adding output of type %s" % out.type)
            output.append(out)

        self._log.debug("output dep_m: %s %s" % (self.name, str(dep_m)))
        self._log.debug("output[2]: %s" % str(output))

        # Store the result
        self.output = TaskDataOutput(
            changed=self.result.changed,
            dep_m=dep_m,
            output=output)
        
        # Store in cache if successful and caching is enabled
        # Skip cache storage if uptodate is explicitly False
        if (self.result.status == 0 and 
            self.uptodate is not False and
            hasattr(runner, 'cache_providers') and 
            runner.cache_providers):
            
            try:
                # Validate output paths are within rundir
                from pathlib import Path
                if cache_util.validate_output_paths(output, rundir):
                    # Compute cache key (returns None if caching disabled)
                    cache_key = await cache_util.compute_cache_key(
                        self.name,
                        None,  # taskdef not available in TaskNode
                        self.params,
                        inputs,
                        rundir,
                        getattr(runner, 'hash_registry', None)
                    )
                    
                    if cache_key:
                        # Convert output to template with ${{ rundir }} placeholders
                        output_template = cache_util.convert_output_to_template(output, rundir)
                        
                        # Store in cache with no compression (default)
                        from .cache_provider import CompressionType
                        stored = await cache_util.store_in_cache(
                            cache_key,
                            output_template,
                            Path(rundir) if Path(rundir).exists() else None,
                            runner.cache_providers,
                            CompressionType.No,
                            metadata={'task': self.name}
                        )
                        
                        if stored:
                            self._log.info(f"Stored task {self.name} in cache")
                            self.result.cache_stored = True
                else:
                    self._log.warning(f"Task {self.name} outputs reference paths outside rundir, not cacheable")
            except Exception as e:
                self._log.warning(f"Failed to store task in cache: {e}")
        
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
        
    async def _check_uptodate(self, rundir: str, inputs: List[Any], changed: bool) -> Tuple[bool, Optional[dict]]:
        """
        Check if this task is up-to-date.
        Returns (is_uptodate, exec_data) tuple.
        exec_data is loaded from exec.json if uptodate, None otherwise.
        """
        # If uptodate is explicitly False, always run
        if self.uptodate is False:
            self._log.debug("Task %s: uptodate=False, forcing run" % self.name)
            return (False, None)
        
        # If any input has changed, we're not up-to-date
        if changed:
            self._log.debug("Task %s: inputs changed, not up-to-date" % self.name)
            return (False, None)
        
        # Check if exec_data file exists
        exec_file = os.path.join(rundir, "%s.exec_data.json" % self.name)
        if not os.path.exists(exec_file):
            self._log.debug("Task %s: no exec_data file, not up-to-date" % self.name)
            return (False, None)
        
        # Load the exec_data
        try:
            with open(exec_file, 'r') as f:
                exec_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self._log.debug("Task %s: failed to load exec_data: %s" % (self.name, e))
            return (False, None)
        
        # If previous run failed, we're not up-to-date (always re-run failed tasks)
        result_data = exec_data.get("result", {})
        if result_data.get("status", 0) != 0:
            self._log.debug("Task %s: previous run failed (status=%s), not up-to-date" % (
                self.name, result_data.get("status")))
            return (False, None)
        
        # Compare parameters
        saved_params = exec_data.get("params", {})
        current_params = self.params.model_dump() if hasattr(self.params, 'model_dump') else {}
        if saved_params != current_params:
            self._log.debug("Task %s: parameters changed, not up-to-date" % self.name)
            return (False, None)
        
        # Compare inputs signature
        saved_signature = exec_data.get("inputs_signature", [])
        current_signature = [
            {"src": item.src, "seq": item.seq, "type": getattr(item, "type", None)}
            for item in inputs
        ]
        if saved_signature != current_signature:
            self._log.debug("Task %s: inputs signature changed, not up-to-date" % self.name)
            return (False, None)
        
        # If there's a custom uptodate method, call it
        if isinstance(self.uptodate, str) and self.uptodate:
            from .uptodate_callable import UpToDateCallable
            from .uptodate_ctxt import UpToDateCtxt
            
            # Extract memento from exec_data if available
            memento = None
            result_data = exec_data.get("result", {})
            if result_data.get("memento"):
                memento = result_data["memento"]
            
            ctxt = UpToDateCtxt(
                rundir=rundir,
                srcdir=self.srcdir,
                params=self.params,
                inputs=inputs,
                exec_data=exec_data,
                memento=memento
            )
            
            callable = UpToDateCallable(body=self.uptodate, srcdir=self.srcdir)
            try:
                is_uptodate = await callable(ctxt)
                if not is_uptodate:
                    self._log.debug("Task %s: custom uptodate check returned False" % self.name)
                    return (False, None)
            except Exception as e:
                self._log.error("Task %s: uptodate check failed: %s" % (self.name, e))
                return (False, None)
        
        self._log.debug("Task %s: up-to-date" % self.name)
        return (True, exec_data)

    def __hash__(self):
        return id(self)
