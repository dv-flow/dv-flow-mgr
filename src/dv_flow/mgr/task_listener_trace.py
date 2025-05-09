import dataclasses as dc
import json
import time
from typing import Dict, List, TextIO
from .task_node import TaskNode

@dc.dataclass
class TaskListenerTrace(object):
    """Task listener that generates Google Trace Event Format output."""
    
    fp: TextIO  # File to write trace events to
    _free_tids: List = dc.field(default_factory=list)  # Pool of available thread IDs
    _task_tid_map: Dict = dc.field(default_factory=dict)  # Map of tasks to their assigned thread IDs
    _next_tid: int = dc.field(default=1)  # Next thread ID to assign if pool is empty
    _next_flow_id: int = dc.field(default=1)  # Counter for unique flow IDs
    _events: List = dc.field(default_factory=list)  # Store events in memory
    
    def __post_init__(self):
        # Add metadata event
        self._events.append({
            "name": "metadata",
            "ph": "M",
            "pid": 1,
            "tid": 0,
            "args": {
                "name": "Task Execution",
                "timeUnit": "us"
            }
        })

    def close(self):
        """Write the complete trace file and close it."""
        trace = {
            "traceEvents": self._events,
            "displayTimeUnit": "ms"  # Show times in milliseconds in the viewer
        }
        json.dump(trace, self.fp, indent=2)
        self.fp.flush()
        
    def _get_tid(self, task: TaskNode) -> int:
        """Get a thread ID for a task, either from the pool or creating a new one."""
        if task in self._task_tid_map:
            return self._task_tid_map[task]
            
        if len(self._free_tids) > 0:
            tid = self._free_tids.pop()
        else:
            tid = self._next_tid
            self._next_tid += 1
            
        self._task_tid_map[task] = tid
        return tid
        
    def _release_tid(self, task: TaskNode):
        """Return a task's thread ID to the pool."""
        if task in self._task_tid_map:
            tid = self._task_tid_map[task]
            del self._task_tid_map[task]
            self._free_tids.append(tid)

    def event(self, task: TaskNode, reason: str):
        """Record a task execution event.
        
        Args:
            task: The task that generated the event
            reason: Either 'enter' or 'leave' marking start/end of task execution
        """
        # Get/create thread ID for this task
        tid = self._get_tid(task)
        
        # Map the event type
        ph = 'B' if reason == 'enter' else 'E'
            
        # Get current timestamp in microseconds
        ts = int(time.time() * 1_000_000) if reason == "enter" else int(task.end.timestamp() * 1_000_000)

        # Create the duration event
        event = {
            "name": task.name,
            "cat": "task",
            "ph": ph, 
            "pid": 1,
            "tid": tid,
            "ts": ts
        }

        # Store the duration event
        self._events.append(event)

        if reason == "enter":
            # When a task starts, create flow events from all its dependencies
            for need, _ in task.needs:
                flow_id = self._next_flow_id
                self._next_flow_id += 1

                # # Add flow end event connecting to this task
                # flow_end = {
                #     "name": f"{need.name} -> {task.name}",
                #     "cat": "flow",
                #     "ph": "e",  # Flow end
                #     "pid": 1,
                #     "tid": tid,  # Target task's thread
                #     "ts": ts,
                #     "id": flow_id,
                #     "bp": "e"  # Connect to enclosing slice
                # }
                # self._events.append(flow_end)

                # # Add flow start event from dependency
                # flow_start = {
                #     "name": f"{need.name} -> {task.name}",
                #     "cat": "flow",
                #     "ph": "b",  # Flow begin
                #     "pid": 1,
                #     "tid": self._task_tid_map.get(need, 0),  # Source task's thread
                #     "ts": int(need.end.timestamp() * 1_000_000) if need.end else ts,
                #     "id": flow_id,
                #     "bp": "e"  # Connect to enclosing slice
                # }
                # self._events.append(flow_start)

        elif reason == 'leave':
            # For completed tasks, emit flow start events
            if task.result:
                event["args"] = {
                    "status": task.result.status,
                    "changed": task.result.changed
                }

                # Find any tasks that depend on this one and create flow events
                for dep_task, dep_tid in self._task_tid_map.items():
                    if any(need[0] is task for need in dep_task.needs):
                        # # Create flow start event
                        # flow = {
                        #     "name": f"{task.name} -> {dep_task.name}",
                        #     "cat": "flow",
                        #     "ph": "s",  # Flow start
                        #     "pid": 1,
                        #     "tid": tid,  # Source task's thread
                        #     "ts": ts,  # Use task end time
                        #     "id": self._next_flow_id,
                        #     "bp": "e"  # Connect to enclosing slice
                        # }
                        # self._events.append(flow)

                        # # Create flow end event
                        # flow_end = {
                        #     "name": f"{task.name} -> {dep_task.name}",
                        #     "cat": "flow",
                        #     "ph": "f",  # Flow finish
                        #     "pid": 1,
                        #     "tid": dep_tid,  # Target task's thread
                        #     "ts": ts,  # Will be updated when target task starts
                        #     "id": self._next_flow_id,
                        #     "bp": "e"  # Connect to enclosing slice
                        # }
                        # self._events.append(flow_end)
                        self._next_flow_id += 1

            self._release_tid(task)
