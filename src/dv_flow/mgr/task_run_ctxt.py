import asyncio
import dataclasses as dc
from pydantic import BaseModel, ConfigDict, Field
import os
import logging
from typing import Callable, Dict, List, Optional, TYPE_CHECKING, Union
from .task_data import TaskMarker, SeverityE, TaskMarkerLoc, TaskDataOutput
from .task_node_ctxt import TaskNodeCtxt

class ExecInfo(BaseModel):
    cmd : List[str] = Field(default_factory=list)
    status : int = Field(default=0)

class ExecCmd(BaseModel):
    """Describes a command to be executed by exec_parallel.
    
    Attributes:
        cmd: List of command arguments (e.g., ['ls', '-la'])
        logfile: Optional log file name for command output
        cwd: Optional working directory (defaults to task rundir)
        env: Optional environment variables (defaults to task env)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    cmd : List[str] = Field(default_factory=list)
    logfile : Optional[str] = Field(default=None)
    cwd : Optional[str] = Field(default=None)
    env : Optional[Dict[str, str]] = Field(default=None)

if TYPE_CHECKING:
    from .task_runner import TaskRunner
    from .task_node import TaskNode

@dc.dataclass
class TaskRunCtxt(object):
    runner : 'TaskRunner'
    ctxt : TaskNodeCtxt
    rundir : str

    _markers : List[TaskMarker] = dc.field(default_factory=list)
    _exec_info : List[ExecInfo] = dc.field(default_factory=list)
    _log : logging.Logger = dc.field(default_factory=lambda: logging.getLogger("TaskRunCtxt"))
    _exec_start_callback : callable = dc.field(default=None)
    _exec_end_callback : callable = dc.field(default=None)

    @property
    def root_pkgdir(self):
        return self.ctxt.root_pkgdir
    
    @property
    def root_rundir(self):
        return self.ctxt.root_rundir
    
    @property
    def env(self):
        return self.ctxt.env if self.ctxt is not None else os.environ
    
    def mkDataItem(self, type, **kwargs):
        """
        Create a data item in the task's rundir. The data item will be
        created in the task's rundir, and will be available to the
        task's implementation.
        """
        try:
            item = self.runner.mkDataItem(
                type=type,
                **kwargs)
        except Exception as e:
            self.error("Failed to create data item: %s" % str(e))
            raise e
        return item
    
    async def exec_parallel(self, 
                            cmds: List[ExecCmd],
                            logfilters: Dict[int, callable] = None) -> List[int]:
        """
        Execute multiple commands in parallel, subject to nproc limits.
        
        Each command runs independently, respecting the exec_semaphore
        concurrency limits. Returns an array of status codes corresponding
        to each command in the input array.
        
        Args:
            cmds: List of ExecCmd objects describing commands to run
            logfilters: Optional dict mapping command index to logfilter callable
        
        Returns:
            List of integer status codes, one per command in same order as input
            
        Example:
        
        .. code-block:: python
        
            from dv_flow.mgr.task_run_ctxt import ExecCmd
            
            cmds = [
                ExecCmd(cmd=['gcc', '-c', 'file1.c'], logfile='compile1.log'),
                ExecCmd(cmd=['gcc', '-c', 'file2.c'], logfile='compile2.log'),
                ExecCmd(cmd=['gcc', '-c', 'file3.c'], logfile='compile3.log'),
            ]
            statuses = await runner.exec_parallel(cmds)
            # statuses[0] = exit code for file1.c compile
            # statuses[1] = exit code for file2.c compile
            # statuses[2] = exit code for file3.c compile
        """
        if logfilters is None:
            logfilters = {}
        
        async def run_one(index: int, cmd_desc: ExecCmd) -> int:
            """Run a single command with semaphore gating"""
            return await self.exec(
                cmd=cmd_desc.cmd,
                logfile=cmd_desc.logfile,
                logfilter=logfilters.get(index),
                cwd=cmd_desc.cwd,
                env=cmd_desc.env
            )
        
        # Create tasks for all commands
        tasks = [run_one(i, cmd) for i, cmd in enumerate(cmds)]
        
        # Execute all in parallel (semaphore inside exec() gates actual process execution)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error status and log
        statuses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.error("Command %d failed with exception: %s" % (i, str(result)))
                statuses.append(-1)
            else:
                statuses.append(result)
        
        return statuses

    async def exec(self, 
                   cmd : List[str],
                   logfile=None,
                   logfilter=None,
                   cwd=None,
                   env=None):
        """
        Executes a command as part of the task's implementation.
        Output from the command will be saved to the specified logfile,
        or to a default logfile if not specified. If the command
        fails, an error marker will be added.

        Example:
        
        .. code-block:: python

            status |= await runner.exec(['ls', '-l'], logfile='ls.log')

        """
        if logfile is None:
            logfile = "cmd_%d.log" % (self._exec_info.__len__() + 1)

        if env is None:
            env = self.env

        # Log command and env differences
        try:
            base_env = self.env if self.ctxt is not None else os.environ
            diff_items = []
            for k, v in env.items():
                bv = base_env.get(k)
                if bv != v:
                    diff_items.append(f"{k}={v}")
            diff_str = ", ".join(diff_items)
            # Log via logging system and include task name if available
            # Task name comes from the active TaskNode; include it if available
            task_name = getattr(getattr(self.runner, '_current_task', None), 'name', None)
            prefix = f"[{task_name}] " if task_name else ""
            self._log.info(prefix + f"exec: cmd={' '.join(cmd)}" + (f" env_diff: {diff_str}" if diff_items else ""))
        except Exception:
            pass

        # Acquire exec semaphore if available (gates on actual process execution)
        semaphore = getattr(self.runner, '_exec_semaphore', None)
        if semaphore is not None:
            await semaphore.acquire()
        
        # Notify exec start
        if self._exec_start_callback is not None:
            self._exec_start_callback()
        
        try:
            fp = open(os.path.join(self.rundir, logfile), "w")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=fp,
                stderr=asyncio.subprocess.STDOUT,
                cwd=(cwd if cwd is not None else self.rundir),
                env=env)
            fp.close()
            
            status = await proc.wait()

            self._exec_info.append(ExecInfo(cmd=cmd, status=status))

            if status != 0:
                self.error("Command failed: %s" % " ".join(cmd))

            if logfilter is not None:
                with open(os.path.join(self.rundir, logfile), "r") as fp:
                    for line in fp.readlines():
                        if logfilter(line):
                            self.info(line.strip())
                    logfilter("")

            return status
        finally:
            # Notify exec end
            if self._exec_end_callback is not None:
                self._exec_end_callback()
            
            # Release exec semaphore
            if semaphore is not None:
                semaphore.release()

    def create(self, path, content):
        """Create a file in the task's rundir"""
        if not os.path.isabs(path):
            path = os.path.join(self.rundir, path)
        
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        with open(path, "w") as fp:
            fp.write(content)

    def add_marker(self, marker : TaskMarker):
        self._markers.append(marker)

    def marker(self, msg : str, severity : SeverityE, loc : TaskMarkerLoc=None):
        """Add a marker related to the task's execution"""
        if loc is not None:
            self._markers.append(TaskMarker(msg=msg, severity=severity, loc=loc))
        else:
            self._markers.append(TaskMarker(msg=msg, severity=severity))

    def error(self, msg : str, loc : TaskMarkerLoc=None):
        """Add an error marker related to the task's execution"""
        self.marker(msg=msg, severity=SeverityE.Error, loc=loc)

    def info(self, msg : str, loc : TaskMarkerLoc=None):
        """Add an error marker related to the task's execution"""
        self.marker(msg=msg, severity=SeverityE.Info, loc=loc)
    
    async def run_subgraph(
        self, 
        tasks: Union['TaskNode', List['TaskNode']],
        name: str = None,
        timeout: float = None
    ) -> Union[TaskDataOutput, List[TaskDataOutput]]:
        """
        Execute a sub-graph of tasks dynamically during task execution.
        
        This schedules the tasks into the current execution schedule,
        respecting dependencies and resource constraints. The call
        blocks until all tasks complete.
        
        Args:
            tasks: TaskNode or list of TaskNodes to execute
            name: Optional name prefix for sub-tasks (for debugging)
            timeout: Optional timeout in seconds (None = no timeout)
            
        Returns:
            TaskDataOutput or list of TaskDataOutput from terminal tasks
            
        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            Exception: If sub-graph execution fails
            
        Example:
            
            .. code-block:: python
            
                async def run(ctxt, input):
                    # Create dynamic tasks
                    task1 = ctxt.mkTaskNode("type1", name="task1")
                    task2 = ctxt.mkTaskNode("type2", name="task2", needs=[task1])
                    
                    # Execute dynamically with timeout
                    results = await ctxt.run_subgraph([task1, task2], timeout=30.0)
                    
                    return TaskDataResult(status=0, output=results)
        """
        # Check if runner supports dynamic scheduling
        if hasattr(self.runner, 'schedule_subgraph'):
            try:
                return await self.runner.schedule_subgraph(tasks, name, timeout)
            except RuntimeError as e:
                # Fall through to fallback
                self._log.debug("Dynamic scheduling not available: %s" % str(e))
        
        # Fallback to nested runner for backward compatibility
        self._log.info("Using nested runner for sub-graph execution")
        from .task_runner import TaskSetRunner
        
        runner = TaskSetRunner(
            rundir=self.rundir,
            nproc=1,
            env=self.env
        )
        
        return await runner.run(tasks)
