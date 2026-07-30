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

def collect_task_params(task):
    """Return (definitions, types) for `task`, **including params inherited via
    `uses:`**, nearest declaration winning.

    `Task.param_defs` holds only the params the task declares itself; the
    inherited ones are merged later, when the node's `paramT` is built. So a
    task's own `param_defs` is not the set of params it actually has, and code
    that treats it that way under-reports a derived task (it will not list, and
    will refuse to override, anything the base declared). This walks the chain
    base-first so a derived declaration overwrites the inherited one.
    """
    definitions = {}
    types = {}
    for t in reversed(list(iter_uses_chain(task))):
        param_defs = getattr(t, 'param_defs', None)
        if param_defs is None:
            continue
        definitions.update(param_defs.definitions)
        types.update(param_defs.types)
    return definitions, types


def collect_param_value_sets(task):
    """{param: ValueSet} in effect for `task`, nearest declaration winning.

    Separate from `collect_task_params` because a value set **inherits
    independently of the value**: a derived task that re-declares a param to
    change its default, and says nothing about `values:`, keeps the base's set
    and is checked against it. That is precisely the case that would go
    unchecked if the set lived on a separate CLI declaration instead of the
    parameter.

    A task that does re-declare `values:` replaces the inherited set outright
    (narrowing or widening it); per-value merging has no answer for "how do I
    remove an inherited value?".
    """
    sets = {}
    for t in reversed(list(iter_uses_chain(task))):
        param_defs = getattr(t, 'param_defs', None)
        if param_defs is None:
            continue
        for name, pdef in param_defs.definitions.items():
            vs = getattr(pdef, 'values', None)
            if vs is not None:
                sets[name] = vs
    return sets


def collect_param_cli(task):
    """{param: CliOpt} for the params `task` exposes as command-line options.

    Inherits along `uses:` **per parameter**, exactly as `collect_param_value_sets`
    does and for the same reason: a derived task that re-declares a param to
    change its default, saying nothing about `cli:`, keeps the base's flag. A
    derived task removes an inherited flag by re-declaring the param with
    `cli: false` -- which is the whole reason absence and `false` are stored
    distinguishably (see ParamDef._normalize_cli).
    """
    opts = {}
    for t in reversed(list(iter_uses_chain(task))):
        param_defs = getattr(t, 'param_defs', None)
        if param_defs is None:
            continue
        for name, pdef in param_defs.definitions.items():
            cli = getattr(pdef, 'cli', None)
            if cli is None:
                continue
            if cli is False:
                opts.pop(name, None)
            else:
                opts[name] = cli
    return opts


@dc.dataclass
class Need(object):
    task : 'Task'
    cond : str = None

@dc.dataclass
class StrategyGenerate(object):
    shell : str = "pytask"
    run : str = None

@dc.dataclass
class SelectSpec(object):
    """A resolved `select:` family: the axes with their members expanded, how a
    cell is named, and what the bare family name means.

    Resolved at load (unlike a matrix, whose axes are expanded at graph build)
    because the cells are declared tasks -- they have to exist before anything
    can reference one by name."""
    axes : Dict[str, List[Any]] = dc.field(default_factory=dict)
    key : str = None
    # 'alias' (the family is one cell), 'all' (a gate over every cell), or
    # 'none' (only cells are addressable).
    mode : str = "alias"
    # For mode == 'alias': {axis: value-or-expression} chosen at graph build.
    default : Dict[str, Any] = dc.field(default_factory=dict)
    # Cell key -> {axis: value}, in cartesian order. The catalog itself.
    cells : Dict[str, Dict[str, Any]] = dc.field(default_factory=dict)

@dc.dataclass
class Strategy(object):
    generate : StrategyGenerate = None
    matrix : Dict[str, List[Any]] = dc.field(default_factory=dict)
    select : SelectSpec = None

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
    # Whether `consumes:` was actually declared. `consumes` itself is defaulted
    # to ConsumesE.All for the engine, so it cannot answer this -- and reading
    # the default as an authored claim is what made the dataflow check vacuous.
    consumes_declared : bool = False
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
    # A cell of a `select:` family: the family task it belongs to and the axis
    # values that identify it. Set on the per-cell tasks registered in the
    # package namespace at load; the builder uses them to bind `this`/`matrix`
    # while the cell's node is constructed. None on every other task.
    select_family : 'Task' = None
    select_bindings : Dict[str, Any] = None
    # A COMMAND-LINE partial cell key (`dfm run sim-img.prof`): the axes it
    # named, with the rest left to the family's default. Set on a throwaway copy
    # of the family task by CLITaskResolver; never on a declared task, because a
    # flow file must name a cell in full (a partial key would change meaning
    # when a default moved).
    select_partial : Dict[str, Any] = None
    run : str = None
    # Directory of the file that *declared* `run`, which is not necessarily
    # this task's own srcdir: an inherited body carries its author's
    # directory along the `uses` chain. Load-time expansion used to get this
    # for free by evaluating the body where it was written; now that the
    # body is expanded per node at graph build, the binding has to be
    # carried explicitly or `${{ srcdir }}` silently resolves to the *using*
    # task's directory.
    run_srcdir : str = None
    shell : str = "bash"
    # May only be reached via `uses:` or as an override replacement.
    # (Formerly one half of `template:`, which also meant "defer run
    # expansion" -- that half is now how every task works.)
    abstract : bool = False
    # Python callable ('module:function') that elaborates this task type at
    # graph-build time (populated from TaskDef.elaborate). Resolved along the
    # `uses` chain by TaskGraphBuilder._resolve_elaborator.
    elaborate : str = None
    # End-of-run summary for this task when it is the task being run: either a
    # 'module:function' string or a SummaryDef (populated from TaskDef.summary).
    # Resolved along the `uses` chain by resolve_task_summary.
    summary : Any = None
    tags : List['Type'] = dc.field(default_factory=list)
    # Check instances this task must satisfy (from TaskDef.requires). Same shape
    # as `tags` -- parameterized type instances -- but consulted by the builder
    # rather than by whoever reads tags. Accumulated along `uses` by
    # TaskGraphBuilder._resolve_requires.
    requires : List['Type'] = dc.field(default_factory=list)
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

