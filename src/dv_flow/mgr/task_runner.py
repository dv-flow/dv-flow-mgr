#****************************************************************************
#* task_runner.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import asyncio
import enum
import json
import os
import re
import dataclasses as dc
import logging
from datetime import datetime
from toposort import toposort
from typing import Any, Callable, ClassVar, Dict, List, Set, Tuple, Union
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node import TaskNode, RundirE
from .dynamic_scheduler import DynamicScheduler

class TaskState(enum.Enum):
    """State of a task in the execution pipeline"""
    NOT_STARTED = enum.auto()   # Task exists but not yet ready
    READY = enum.auto()          # Dependencies met, ready to launch
    SCHEDULED = enum.auto()      # Queued for execution
    RUNNING = enum.auto()        # Currently executing
    COMPLETED = enum.auto()      # Finished (success or failure)
    SKIPPED = enum.auto()        # Skipped due to dependency failure

@dc.dataclass
class TaskRunner(object):
    rundir : str
    env : Dict[str, str] = dc.field(default=None)

    # List of [Listener:Callable[Task],Recurisve:bool]
    listeners : List[Tuple[Callable[['Task'],'Reason'], bool]] = dc.field(default_factory=list)

    _log : ClassVar = logging.getLogger("TaskRunner")

    def __post_init__(self):
        if self.env is None:
            self.env = os.environ.copy()

    def enter(self):
        for l in self.listeners:
            l[0](self, "start")

    def leave(self):
        for l in self.listeners:
            l[0](self, "end")

    def add_listener(self, l, recursive=False):
        self.listeners.append((l, recursive))

    def _notify(self, task : 'Task', reason : 'Reason'):
        for listener in self.listeners:
            listener[0](task, reason)

    async def do_run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        return await self.run(task, memento)
    
    async def exec(cmd, **kwargs):
        # Acquire job token
        # Create 
        pass

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        pass

@dc.dataclass
class TaskSetRunner(TaskRunner, DynamicScheduler):
    builder : 'TaskGraphBuilder' = None
    nproc : int = -1
    status : int = 0
    force_run : bool = False
    cache_providers : List = dc.field(default_factory=list)
    hash_registry : 'ExtRgy' = None
    enable_server : bool = True  # Enable DFM command server for LLM integration

    _anon_tid : int = 1
    _exec_semaphore : asyncio.Semaphore = dc.field(default=None, init=False)
    
    # State tracking
    _task_state : Dict[TaskNode, TaskState] = dc.field(default_factory=dict, init=False)
    _ready_queue : asyncio.Queue = dc.field(default=None, init=False)
    _dep_map : Dict[TaskNode, Set[TaskNode]] = dc.field(default_factory=dict, init=False)
    
    # Command server for LLM integration
    _command_server : 'DfmCommandServer' = dc.field(default=None, init=False)

    _log : ClassVar = logging.getLogger("TaskSetRunner")

    def __post_init__(self):
        super().__post_init__()
        if self.nproc == -1:
            self.nproc = os.cpu_count()
        
        # Initialize exec semaphore to gate process execution
        self._exec_semaphore = asyncio.Semaphore(self.nproc)
        
        # Initialize ready queue
        self._ready_queue = asyncio.Queue()
        
        # Initialize dynamic scheduler
        self._init_dynamic_scheduler()
    
    @property
    def server_socket_path(self) -> str:
        """Get the command server socket path, if server is running"""
        if self._command_server:
            return self._command_server.socket_path
        return None

    async def run(self, task : Union[TaskNode,List[TaskNode]]):
        # Ensure that the rundir exists or can be created
        self.enter()

        if not os.path.isdir(self.rundir):
            os.makedirs(self.rundir)

        if not os.path.isdir(os.path.join(self.rundir, "cache")):
            os.makedirs(os.path.join(self.rundir, "cache"))

        # Start command server for LLM integration (if enabled and builder available)
        if self.enable_server and self.builder is not None:
            from .dfm_server import DfmCommandServer
            self._command_server = DfmCommandServer(
                runner=self,
                builder=self.builder
            )
            await self._command_server.start()
            
            # Set environment variable for child processes
            self.env["DFM_SERVER_SOCKET"] = self._command_server.socket_path
            self.env["DFM_SESSION_RUNDIR"] = self.rundir
            self._log.info(f"Command server started at {self._command_server.socket_path}")

        # Enable dynamic scheduling
        self._dynamic_enabled = True
        
        # Initialize state tracking
        self._task_state.clear()
        self._pending_tasks.clear()
        self._task_completion_events.clear()
        
        src_memento = None
        dst_memento = {}
        if os.path.isfile(os.path.join(self.rundir, "cache", "mementos.json")):
            try:
                with open(os.path.join(self.rundir, "cache", "mementos.json"), "r") as f:
                    src_memento = json.load(f)
            except Exception as e:
                src_memento = {}
        else:
            src_memento = {}

        # Build dependency map
        self._dep_map = self.buildDepMap(task)

        if self._log.isEnabledFor(logging.DEBUG):
            self._log.debug("Deps:")
            for t,value in self._dep_map.items():
                self._log.debug("  Task: %s", str(t.name))
                for v in value:
                    self._log.debug("  - %s", str(v.name))

        # Initialize state for all tasks
        for t in self._dep_map.keys():
            self._task_state[t] = TaskState.NOT_STARTED
            self._task_completion_events[t.name] = asyncio.Event()
            self._pending_tasks[t.name] = t

        # Find initial ready tasks (no dependencies)
        for t, deps in self._dep_map.items():
            if not deps:  # No dependencies
                self._task_state[t] = TaskState.READY
                await self._ready_queue.put(t)
                self._log.debug("Initial ready task: %s" % t.name)

        active_task_l = []
        done_task_s = set()
        self.status = 0
        
        # Start unified task processor
        processor_task = asyncio.create_task(
            self._process_ready_and_dynamic_tasks(active_task_l, done_task_s, src_memento, dst_memento))
        
        try:
            # Wait for processor to finish
            await processor_task
                    
        finally:
            # Disable dynamic scheduling
            self._dynamic_enabled = False
            
            # Stop command server
            if self._command_server:
                await self._command_server.stop()
                self._command_server = None

        with open(os.path.join(self.rundir, "cache", "mementos.json"), "w") as f:
            json.dump(dst_memento, f)

        self.leave()

        if self.status == 0:
            if isinstance(task, list):
                for t in task:
                    if t.output is None:
                        raise Exception("Task %s did not produce output" % t.name)
                return list(t.output for t in task)
            else:
                if task.output is None:
                    raise Exception("Task %s did not produce output" % task.name)
                return task.output
        else:
            return None
        
    def mkDataItem(self, type, **kwargs):
        if self.builder is None:
            raise Exception("TaskSetRunner.mkDataItem() requires a builder")
        return self.builder.mkDataItem(type, **kwargs)
    
    async def _launch_task(
        self,
        t: TaskNode,
        active_task_l: List,
        src_memento: dict,
        dst_memento: dict
    ):
        """Launch a single task with proper setup and dependency waiting"""
        
    async def _launch_task(
        self,
        t: TaskNode,
        active_task_l: List,
        src_memento: dict,
        dst_memento: dict
    ):
        """Launch a single task with proper setup"""
        
        # Update state to running
        self._task_state[t] = TaskState.RUNNING
        
        # Dependencies should already be satisfied (checked before enqueuing)
        # But double-check for safety
        for dep, _ in t.needs:
            if dep.name in self._task_completion_events:
                event = self._task_completion_events[dep.name]
                if not event.is_set():
                    self._log.warning("Task %s launched but dependency %s not complete!" % (t.name, dep.name))
                    await event.wait()
        
        memento = src_memento.get(t.name, None)
        invalid_chars_pattern = r'[\/:*?"<>|#%&{}\$\\!\'`;=@+]'

        # TaskNode rundir is a list of path elements relative
        # to the root rundir
        rundir_split = t.rundir
        if not isinstance(t.rundir, list):
            rundir_split = t.rundir.split('/')

        # Determine base rundir: absolute first segment or anchor to self.rundir
        if len(rundir_split) > 0 and os.path.isabs(rundir_split[0]):
            rundir = rundir_split[0]
            segs = rundir_split[1:]
        else:
            rundir = self.rundir
            segs = rundir_split

        for rundir_e in segs:
            rundir_e = re.sub(invalid_chars_pattern, '_', rundir_e)
            rundir = os.path.join(rundir, rundir_e)

        if not os.path.isdir(rundir):
            try:
                os.makedirs(rundir, exist_ok=True)
            except Exception as e:
                print("Failed to create rundir %s: %s" % (rundir, str(e)), flush=True)
                raise e

        self._log.debug("Launching task %s" % t.name)
        self._notify(t, "enter")
        t.start = datetime.now()
        # Track current task for logging context
        setattr(self, '_current_task', t)
        coro = asyncio.Task(t.do_run(
            self,
            rundir,
            memento)) 
        active_task_l.append((t, coro))
    
    def _skip_task(self, task: TaskNode, done_task_s: Set[TaskNode]):
        """Mark a task as skipped (not executed due to failure)"""
        self._log.debug("Skipping task %s" % task.name)
        
        # Mark as skipped
        done_task_s.add(task)
        self._task_state[task] = TaskState.SKIPPED
        
        # Create dummy result
        task.result = TaskDataResult(status=1, output=[], changed=False)
        task.output = TaskDataOutput(changed=False, dep_m={}, output=[])
        
        # Signal completion event so dependent tasks can proceed
        if task.name in self._task_completion_events:
            self._task_completion_events[task.name].set()
            if task.name in self._pending_tasks:
                del self._pending_tasks[task.name]
        
        # Check if this completes any sub-graphs
        for sg_id in list(self._active_subgraphs.keys()):
            self._complete_subgraph(sg_id, done_task_s)
    
    async def _process_ready_and_dynamic_tasks(
        self,
        active_task_l: List,
        done_task_s: Set[TaskNode],
        src_memento: dict,
        dst_memento: dict
    ):
        """
        Unified processor for ready tasks and dynamic tasks.
        
        Event-driven loop that waits for:
        1. Task completions -> mark complete -> check dependents
        2. Ready tasks from queue -> launch them
        3. Dynamic tasks from queue -> add to dep_map -> check if ready
        """
        self._log.debug("Task processor started")
        
        # Persistent queue waiters (reused to avoid recreating)
        ready_queue_waiter = None
        dynamic_queue_waiter = None
        
        while True:
            # Check exit condition: all tasks done and no more work
            all_done = all(
                state in (TaskState.COMPLETED, TaskState.SKIPPED) 
                for state in self._task_state.values()
            )
            
            if all_done and len(active_task_l) == 0 and self._ready_queue.empty():
                self._log.debug("Task processor: all tasks done, exiting")
                break
            
            # Deadlock detection: no active tasks, nothing ready, but tasks still pending
            if len(active_task_l) == 0 and self._ready_queue.empty() and not all_done:
                stuck_tasks = [task.name for task, state in self._task_state.items() 
                              if state == TaskState.NOT_STARTED]
                if stuck_tasks:
                    self._log.error("Deadlock detected: %d tasks stuck in NOT_STARTED state" % len(stuck_tasks))
                    self._log.error("Stuck tasks: %s" % ", ".join(stuck_tasks))
                    for task, state in list(self._task_state.items()):
                        if state == TaskState.NOT_STARTED:
                            self._skip_task(task, done_task_s)
                    continue
                else:
                    self._log.error("Deadlock: no active tasks, queue empty, but not all done. States:")
                    for task, state in self._task_state.items():
                        self._log.error("  %s: %s" % (task.name, state))
                    break
            
            try:
                # Build wait set for all possible events
                wait_tasks = []
                
                # 1. Active task completions
                if active_task_l:
                    wait_tasks.extend([at[1] for at in active_task_l])
                
                # 2. Ready queue - create waiter if needed
                if ready_queue_waiter is None or ready_queue_waiter.done():
                    ready_queue_waiter = asyncio.create_task(self._ready_queue.get())
                wait_tasks.append(ready_queue_waiter)
                
                # 3. Dynamic queue - create waiter if needed
                if dynamic_queue_waiter is None or dynamic_queue_waiter.done():
                    dynamic_queue_waiter = asyncio.create_task(self._dynamic_task_queue.get())
                wait_tasks.append(dynamic_queue_waiter)
                
                # Wait for ANY event to complete
                done, pending = await asyncio.wait(
                    wait_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed events - but prioritize task completions over queue events
                # to avoid launching too many tasks at once
                task_completions = []
                has_ready_task = False
                has_dynamic_task = False
                
                for completed in done:
                    # Check if it's a task completion
                    is_task_completion = False
                    for at in active_task_l:
                        if at[1] == completed:
                            is_task_completion = True
                            task_completions.append(completed)
                            break
                    
                    if not is_task_completion:
                        if completed == ready_queue_waiter:
                            has_ready_task = True
                        elif completed == dynamic_queue_waiter:
                            has_dynamic_task = True
                
                # Handle all task completions first
                if task_completions:
                    self._handle_completions(active_task_l, done_task_s, task_completions, dst_memento)
                
                # Then handle ONE ready task (to avoid launching too many at once)
                if has_ready_task:
                    ready_task = ready_queue_waiter.result()
                    ready_queue_waiter = None  # Will be recreated next iteration
                    
                    if self._task_state.get(ready_task) != TaskState.READY:
                        self._log.warning("Task %s in ready queue but state is %s" % 
                                         (ready_task.name, self._task_state.get(ready_task)))
                    else:
                        if self.status == 0:
                            self._task_state[ready_task] = TaskState.SCHEDULED
                            await self._launch_task(ready_task, active_task_l, src_memento, dst_memento)
                        else:
                            self._skip_task(ready_task, done_task_s)
                
                # Then handle ONE dynamic task
                if has_dynamic_task:
                    item = dynamic_queue_waiter.result()
                    dynamic_queue_waiter = None  # Will be recreated next iteration
                    
                    if item is not None:  # Not a sentinel
                        subgraph_id = item['id']
                        self._dynamic_log.debug("Processing sub-graph %d from queue" % subgraph_id)
                        
                        for task, deps in item['dep_map'].items():
                            if task not in self._task_state:
                                self._dep_map[task] = deps
                                self._task_state[task] = TaskState.NOT_STARTED
                                self._pending_tasks[task.name] = task
                                self._task_completion_events[task.name] = asyncio.Event()
                                self._dynamic_log.debug("  Added dynamic task %s" % task.name)
                                
                                if self._is_task_ready(task):
                                    self._task_state[task] = TaskState.READY
                                    await self._ready_queue.put(task)
                                    self._dynamic_log.debug("  Task %s is immediately ready" % task.name)
                    
            except Exception as e:
                self._log.error("Error in task processor: %s" % e)
                import traceback
                import sys
                traceback.print_exc(file=sys.stdout)
        
        # Clean up any pending waiters
        if ready_queue_waiter and not ready_queue_waiter.done():
            ready_queue_waiter.cancel()
        if dynamic_queue_waiter and not dynamic_queue_waiter.done():
            dynamic_queue_waiter.cancel()
        
        self._log.debug("Task processor stopped")
    
    def _is_task_ready(self, task: TaskNode) -> bool:
        """Check if all dependencies of a task are completed"""
        for dep, _ in task.needs:
            dep_state = self._task_state.get(dep, TaskState.NOT_STARTED)
            if dep_state != TaskState.COMPLETED:
                return False
        return True
    
    def _handle_completions(self, active_task_l, done_task_s, done_l, dst_memento):
        """
        Handle completed tasks and check if any dependents become ready.
        This replaces the old _completeTasks but adds dependent checking.
        """
        for d in done_l:
            for i in range(len(active_task_l)):
                if active_task_l[i][1] == d:
                    completed_task = active_task_l[i][0]
                    completed_task.end = datetime.now()
                    
                    # Mark as completed
                    done_task_s.add(completed_task)
                    self._task_state[completed_task] = TaskState.COMPLETED
                    
                    # Signal completion event
                    if completed_task.name in self._task_completion_events:
                        self._task_completion_events[completed_task.name].set()
                        self._pending_tasks.pop(completed_task.name, None)  # Use pop to avoid KeyError
                        self._log.debug("Completed: %s" % completed_task.name)
                    
                    # Check sub-graphs
                    for sg_id in list(self._active_subgraphs.keys()):
                        self._complete_subgraph(sg_id, done_task_s)
                    
                    # Handle result
                    if completed_task.result is None:
                        raise Exception("Task %s did not produce a result" % completed_task.name)
                    if completed_task.result.memento is not None:
                        dst_memento[completed_task.name] = completed_task.result.memento.model_dump()
                    else:
                        dst_memento[completed_task.name] = None
                    self.status |= completed_task.result.status 
                    if self.status:
                        self._log.debug("Task %s failed with status %d" % (completed_task.name, completed_task.result.status))
                    self._notify(completed_task, "leave")
                    active_task_l.pop(i)
                    
                    # KEY: Check all tasks that depend on this one
                    self._check_and_enqueue_dependents(completed_task)
                    break
    
    def _check_and_enqueue_dependents(self, completed_task: TaskNode):
        """
        Check all tasks in dep_map that depend on completed_task.
        If a dependent is now ready (all deps complete), enqueue it.
        """
        for task, deps in self._dep_map.items():
            # Skip if not dependent on completed_task
            if completed_task not in deps:
                continue
            
            # Skip if not in NOT_STARTED state
            if self._task_state.get(task) != TaskState.NOT_STARTED:
                continue
            
            # Check if all dependencies are now complete
            if self._is_task_ready(task):
                self._task_state[task] = TaskState.READY
                self._ready_queue.put_nowait(task)
                self._log.debug("Task %s now ready (dep %s completed)" % (task.name, completed_task.name))
    
    
        
    def buildDepMap(self, task : Union[TaskNode, List[TaskNode]]) -> Dict[TaskNode, Set[TaskNode]]:
        tasks = task if isinstance(task, list) else [task]
        dep_m = {}
        self._anon_tid = 1
        for t in tasks:
            self._buildDepMap(dep_m, t)

        return dep_m

    def _buildDepMap(self, dep_m, task : TaskNode):
        if task.name is None:
            task.name = "anon_%d" % self._anon_tid
            self._anon_tid += 1

        if task not in dep_m.keys():
            dep_m[task] = set(task[0] for task in task.needs)
            for need,block in task.needs:
                self._buildDepMap(dep_m, need)

@dc.dataclass
class SingleTaskRunner(TaskRunner):

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        changed = False
        for dep,_ in task.needs:
            changed |= dep.changed

        # TODO: create an evaluator for substituting param values
        eval = None

#        for field in dc.fields(task.params):
#            print("Field: %s" % field.name)

        input = TaskDataInput(
            name=task.name,
            changed=changed,
            srcdir=task.srcdir,
            rundir=self.rundir,
            params=task.params,
            inputs=[],
            memento=memento)

        # TODO: notify of task start
        ret : TaskDataResult = await task.task(self, input)
        # TODO: notify of task complete

        # Store the result
        task.output = TaskDataOutput(
            changed=ret.changed,
            output=ret.output.copy())

        # # By definition, none of this have run, since we just ran        
        # for dep in task.dependents:
        #     is_sat = True
        #     for need in dep.needs:
        #         if need.output is None:
        #             is_sat = False
        #             break
            
        #     if is_sat:
        #         # TODO: queue task for evaluation
        #     pass
        # TODO: 

        return ret
