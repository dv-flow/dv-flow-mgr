
# Tasks
- A task has 0..N dependencies (references to tasks whose output
  data must be available prior to execution of the task)
- The input data available to a task includes
  - Output data from its dependencies
  - Memento data from its prior execution (a memento is a record of task execution)
    - Makes sense to include markers here
  - Locally-specified data (ie task parameters)
- The core implementation of a task is invoked with a
  consolidated set of data that is specified in the task definition.
  - Example: select all FileSet that have kind systemVerilog, verilog, or VHDL 
- The output of a task is comprised of (think of this as a filter?)
  - Output data from its dependencies
  - Memento data from the implementation, including marker information

# Types
- Types are named structures

# Task Parameters
- A task may have parameters. Parameters are singletons, and are
  not extensible from outside. 
- If a task needs to accept outside input, it must select that
  by type from input parameter sets
- Direct parameters
- Task parameters are exposed to task implementation via a type with the task name
- Do we really need this?
- Using explicit types results in one extra layer of indirection
- Still may have to deal with ambiguity...

- name: RunSim
  uses: SimRun
  with:
  - name: simargs
    type: 
      list:
        item: SimArgs
    value: ${{ jq in.[]}}
  - uses: SimArgs
    with:
    - append-list

So... Tasks do not have parameters. 
- Tasks can inject parameter sets into the input set
- Tasks can control what emerges from the task

plusargs: .[] select(uses==SimArgs) | 

# Cross-Task Dataflow
- Cross-task dataflow is comprised of a collection of typed objects
  containing typed fields.
- Augmenting data is done by injecting new object instances into
  the dataset. For example:
  - The dataset contains an object for specifying simulation runtime
    arguments. It contains a directive to append "+UVM_TEST=my_test" 
    to the arguments
  - I add a new runtime-arguments object that contains a directive
    to append "+debug" to the arguments
  - The consumer will see [+UVM_TEST=my_test +debug]


# Data-Combination Rules
- In most cases, data must be flattened in order to use it. For example,
  
- 

# Package Providers
- Packages are resolved through an ordered list of *package providers*
  (`PackageLoader._pkg_providers`), walked first-wins by `findPackage`.
- A provider answers two questions with different guarantees:
  - `findPackage(name)` is **authoritative**: it resolves and parses the
    named package on demand, caches it, and returns `None` if it does not own
    the name. This is the single lazy entry point — a package is parsed the
    first time some provider's `findPackage` reaches it.
  - `getPackageNames()` is **best-effort** enumeration (used by list/discover
    paths). It may be incomplete or empty for search-style providers (e.g. the
    `DV_FLOW_PATH` search), which can only answer "do you have *this* name?".
- The loader caches resolved packages by both name and normalized absolute
  path, so a package reachable both by registry/map name and by a file-path
  import is parsed only once.
- `ExtRgy` (built-in `std`, entry-point plugins, `DV_FLOW_PATH`) and the
  ivpm-generated package map (`PackageMapProvider`) are both just providers in
  this list.

# Lazy Package Loading
- An import by *name* (`- name: foo`, `{name, from}`) is stored in the parent's
  `pkg_m` as a `LazyPackage` placeholder instead of a fully-parsed package.
- `LazyPackage` is a transparent proxy: the dependency's `flow` file is parsed
  the first time a *data* attribute (`task_m`, `type_m`, `pkg_m`, `paramT`, ...)
  is accessed. `name` is known up front, so keying `pkg_m` and reading
  `pkg.name` do not force materialization.
- Unresolvable names are reported at load time via a cheap `canResolve` check
  (provider membership / `hasPackage`) that does not parse the dependency.
- Imports by *path* are parsed eagerly. Building a task graph flattens all
  imported packages, so a graph build materializes every reachable import; the
  deferral therefore benefits load-only paths (introspection, partial
  validation) where an import is never touched.
