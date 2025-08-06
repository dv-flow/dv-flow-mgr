import dataclasses as dc
import json
import time
from typing import Dict, List, TextIO
from .task_node import TaskNode
from .fileset import FileSet

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

    def _get_task_data(self, task: TaskNode) -> dict:
        """Extract serializable task data"""
        data = {}
        
        # Add any parameters
        if hasattr(task, 'params') and task.params:
            # If params is a dataclass or has __dict__, get its fields
            if hasattr(task.params, '__dict__'):
                data['params'] = task.params.__dict__
            elif isinstance(task.params, dict):
                data['params'] = task.params

        # Add inputs if present
        if hasattr(task, 'needs') and task.needs:
            inputs = []
            for need, _ in task.needs:
                if hasattr(need, 'output') and need.output:
                    _items = []
                    for out in need.output.output:
                        if hasattr(out, 'model_dump'):
                            _items.append(out.model_dump())
                    inputs.append({
                        'task': need.name,
                        'data': _items
                    })
            if inputs:
                data['inputs'] = inputs

        return data

    def event(self, task: TaskNode, reason: str):
        """Record a task execution event.
        
        Args:
            task: The task that generated the event
            reason: Either 'enter' or 'leave' marking start/end of task execution
        """
        if reason in ("start", "end"):
            return

        # Get/create thread ID for this task
        tid = self._get_tid(task)
        
        # Map the event type
        ph = 'B' if reason == 'enter' else 'E'
            
        # Get current timestamp in microseconds
        ts = int(time.time() * 1_000_000) if reason == "enter" else int(task.end.timestamp() * 1_000_000)

        # Create the duration event with initial args
        args = {}
        
        # Add task data
        if reason == "enter":
            # Add input data on task start
            input_data = self._get_task_data(task)
            if input_data:
                args = input_data

        elif reason == 'leave':
            if task.result:
                # Add status and change info
                args["status"] = task.result.status
                args["changed"] = task.result.changed
                
                # Add output data if present
                if hasattr(task.result, 'output') and task.result.output:
                    args["output"] = [
                        out.__dict__ if hasattr(out, '__dict__') else out 
                        for out in task.result.output
                    ]

            self._release_tid(task)

        # Create the event with collected args
        event = {
            "name": task.name,
            "cat": "task",
            "ph": ph, 
            "pid": 1,
            "tid": tid,
            "ts": ts,
            "args": args
        }

        # Store the duration event
        self._events.append(event)

        # Add flow event for dependencies
        if reason == "enter":
            # When task starts, add flow event from each dependency
            for need, _ in task.needs:
                # Create flow start from completed task to this one
                flow = {
                    "name": f"{need.name} -> {task.name}",
                    "cat": "flow",
                    "ph": "s",  # Flow start 
                    "pid": 1,
                    "tid": self._task_tid_map.get(need, 0),
                    "ts": int(need.end.timestamp() * 1_000_000) if need.end else ts,
                    "id": self._next_flow_id,
                    "bp": "e"
                }
                self._events.append(flow)
                
                # Create flow finish at the start of this task
                flow_end = {
                    "name": f"{need.name} -> {task.name}",
                    "cat": "flow",
                    "ph": "f",  # Flow finish
                    "pid": 1, 
                    "tid": tid,
                    "ts": ts,
                    "id": self._next_flow_id,
                    "bp": "e"
                }
                self._events.append(flow_end)
                self._next_flow_id += 1
