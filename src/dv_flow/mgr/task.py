import dataclasses as dc
from typing import Any, Callable, Dict, List, Tuple, Union, TYPE_CHECKING
from .srcinfo import SrcInfo
from .task_def import TaskDef, RundirE, PassthroughE, ConsumesE

if TYPE_CHECKING:
    from .param_def_collection import ParamDefCollection


def iter_uses_chain(task):
    """Yield each task along the `uses` chain, most-derived first, guarding
    against cycles. Single source of truth for the `while current: ... current =
    current.uses` walk that was copied across the builder and param-builder
    (param collection, package-name/task-name chains, elaborator lookup)."""
    current = task
    visited = set()
    while current is not None:
        if id(current) in visited:
            break
        visited.add(id(current))
        yield current
        current = getattr(current, 'uses', None)

@dc.dataclass
class Need(object):
    task : 'Task'
    cond : str = None

@dc.dataclass
class StrategyGenerate(object):
    shell : str = "pytask"
    run : str = None

@dc.dataclass
class Strategy(object):
    generate : StrategyGenerate = None
    matrix : Dict[str, List[Any]] = dc.field(default_factory=dict)

@dc.dataclass
class Task(object):
    """
    Type information about a task, linking it into the package
    to which it belongs.

    Needs in the Task class point to the resolved name. Overrides
    are applied when constructing a TaskNode DAG from tasks
    """
    name : str
    desc: str = ""
    doc : str = ""
    paramT : Any = None
    param_defs : 'ParamDefCollection' = None  # NEW: Unevaluated param definitions
    uses : 'Task' = None
    package : 'Package' = None
    iff : str = None
    needs : List[str] = dc.field(default_factory=list)
    consumes : Union[ConsumesE, List[Dict[str, Any]]] = dc.field(default=None)
    produces : Union[List[Dict[str, Any]], None] = dc.field(default=None)
    passthrough : Union[PassthroughE, List[Dict[str, Any]]] = dc.field(default=None)
    rundir : RundirE = None
    uptodate : Union[bool, str, None] = None
    cache : Any = None
    # TODO: strategy / matrix
    subtasks : List['Task'] = dc.field(default_factory=list)
    is_root : bool = False
    is_export : bool = False
    is_local : bool = False
    strategy : Strategy = dc.field(default=None)
    # Deferred `uses` for matrix-strategy body subtasks: when a body task computes
    # its `uses` from a matrix variable (e.g. `uses: uvm-${{ this.test }}`), the
    # binding only exists once the strategy fans out at graph-build time. The raw
    # expression (and its fragment context for name resolution) is stashed here and
    # resolved per matrix cell in TaskGraphBuilder._applyStrategyMatrix.
    uses_expr : str = None
    uses_expr_fragment : str = None
    # Same deferral for `needs`: a matrix body may compute a need from a matrix
    # variable (e.g. `needs: ["${{ this.image }}"]`). Such needs can't resolve at
    # parse time (the binding only exists when the strategy fans out), so the raw
    # expressions are stashed here and resolved per cell in _applyStrategyMatrix.
    needs_expr : List[str] = dc.field(default_factory=list)
    needs_expr_fragment : str = None
    run : str = None
    shell : str = "bash"
    template : bool = False
    # Python callable ('module:function') that elaborates this task type at
    # graph-build time (populated from TaskDef.elaborate). Resolved along the
    # `uses` chain by TaskGraphBuilder._resolve_elaborator.
    elaborate : str = None
    tags : List['Type'] = dc.field(default_factory=list)
    max_failures : int = -1
    on_error : str = None
    srcinfo : SrcInfo = None
    taskdef : 'TaskDef' = None
    # Scoped variables (`let:`) provided to this task's subtree, read via
    # resolve(). Layered into the eval context's __let__ carrier during graph
    # build (see TaskGraphBuilder._apply_let). DEPRECATED — see `set_defs`.
    let : Dict[str, Any] = dc.field(default_factory=dict)
    # Scoped overrides (`set:`) applied to this task's subtree: a list of
    # assignment maps (rebind scoped vars read via ${{ pkg.var }}) and/or scope
    # items ({uses?, path?, set: [...]}). Applied during graph build by
    # TaskGraphBuilder._apply_set. Outer overrides inner; CLI (-D) is the ceiling.
    set_defs : List[Any] = dc.field(default_factory=list)

    @property
    def leafname(self):
        return self.name[self.name.rfind(".")+1:]

    def __post_init__(self):
        if self.name is None:
            self.name = self.task_def.name

    def dump(self):
        task = {
            "name": self.name,
            "paramT": str(type(self.paramT)),
            "rundir": str(self.rundir),
        }

        if self.uses is not None:
            task["uses"] = self.uses.name
        if self.needs is not None and len(self.needs):
            task["needs"] = [n.name for n in self.needs]
        if self.subtasks is not None and len(self.subtasks):
            task["subtasks"] = [t.dump() for t in self.subtasks]
        if self.run is not None:
            task["run"] = self.run
        if self.shell is not None:
            task["shell"] = self.shell
        if self.srcinfo is not None:
            task["srcinfo"] = self.srcinfo.dump()
        if self.produces is not None and len(self.produces):
            task["produces"] = self.produces

        return task

    def __hash__(self):
        return id(self)

