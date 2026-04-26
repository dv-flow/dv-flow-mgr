
# Package Configuration

The elements of a package are loaded in a specific order to enable support
for multiple configurations. 

## Import external packages
Package imports at the package level are imported first. If variables are 
used in the package-import paths, only built-in and environment variables
may be used. Examples:
- ${{ srcdir }}
- ${{ rootdir }}

## Package inheritance hierarchy
Next, the base package and package-level parameters are resolved. The set
of package-level variables consists of:
- Variables declared by the base package(s) (if present)
- Variables declared by the current package

Outer parameter values override inner parameter values. Command-line
parameter overrides overide outer parameter values. For example:

```
package:
  name: p1
  with:
    v1:
      type: str
      value: val1
```

```
package
  name: p2
  imports:
  - "path/p1.yaml"
  uses: p1
  with:
    v1: val1_2
    v2:
      type: str
      value: val2
```

With no command-line overrides, the following parameters are declared
in p2:
- v1: val1_2
- v2: val2

Command-line parameter overrides would further modify these values.

## Load fragments

Next, fragments referenced in the base package are loaded. Paths
to these fragments can use any variables defined thus far. Parameters
that are overridden on the command-line will have the command-line value.

## Select Config

Next, the active configuration is selected. If one has been specified,
either on the command-line or as part of the import statement, the set
declared in the root package and included fragments is searched. If
no config is specified, then:
- If a configuration named 'default' exists, this is used
- Otherwise, not configuration is used

## Apply Configuration
A configuration may contain:
- Imports
- Parameters (with)
- Tasks
- Types
- Fragments

A configuration may inherit from (use) another configuration.

Think of a configuration as inheriting from the package to which 
it applies.

### Load imports
If the configuration specifies imports, these are loaded first. 
Import paths may only reference previously-defined variables. 
Specifically: 
- variables defined in the package
- environment variables
- build-in variables

### Resolve base and parameters
Next, the base configuration (if applicable) is identified. 
Parameter declarations and value specifications from the base configuration 
and the active configuration are applied to the package variables. 
For example:

```
package:
  name: p2
  # ...
  configs:
  - name: default
    with:
      v1: val1_3
      v3: 
        type: int
        value: 25
```

Assuming the 'default' config is applied, package p2 will have the following
variables:
- v1: va1_3
- v2: val2
- v3: 25

### Load fragments
Next, fragments specified in the config are loaded (if applicable). 


## Elaborate Types and Actions
After applying the configuration, tasks and types are elaborated. Type/task
elaboration must take inheritance into account.

```
package:
  name: p1
  tasks:
  - name: t1
  - name: t2
    needs: [t1]
  - name: t3
    needs: [t2]
```

```
package
  name: p2
  uses: p1
  tasks:
  - override: t1

  configs:
  - name: default
    tasks:
    - override t2
```

In the example above:
- p2::t1 overrides p1::t1. This means that p1::t2 actually `needs` p2::t1
- config p2::default overrides t2. This means that p1::t3 actually `needs` p2::default::t2


## Config-Level Task Overrides

Configurations support an `overrides:` section that substitutes tasks in the
graph when the config is active.  This is useful for stubbing out expensive
tasks during fast-iteration builds without modifying the base task graph.

Each override entry uses `task:` or `package:` to identify the target and
`with:` to name the replacement:

```yaml
package:
  name: my_project
  imports:
    - sim_pkg

  configs:
    - name: fast
      overrides:
        - task: sim_pkg.CompileAndSim.Compile
          with: std.Null
        - task: sim_pkg.CompileAndSim.Simulate
          with: std.Null
```

Running with the config active applies the substitutions:

```
dfm run -c fast entry
```

### Addressing nested tasks

Tasks inside compound bodies have fully-qualified names built from the
nesting path:

```yaml
- name: Outer
  body:
    - name: Inner
      body:
        - name: Sub   # -> pkg.Outer.Inner.Sub
```

The override target uses the same fully-qualified path.

### Package-level overrides

Overrides can also be declared at the package level (always active, no config
required) using a simple map syntax:

```yaml
package:
  name: my_project
  overrides:
    sim_pkg.OldLint: my_project.NewLint
```

### Override precedence

When multiple override sources exist, later sources shadow earlier ones:

1. Package-level `overrides:` map (applied first)
2. Config-level `overrides:` list (applied on top)
3. CLI `--override` flags (applied last, highest priority)

If a config inherits from a base config (`uses:`), the base config's
overrides apply first, then the derived config's overrides shadow them.

### Stubbing with std.Null

The built-in `std.Null` task is a no-op that passes inputs through
unchanged.  It is the natural replacement for tasks you want to skip:

```yaml
configs:
  - name: fast
    overrides:
      - task: pkg.ExpensiveTask
        with: std.Null
```

### Overrides vs task-level override:

| Aspect | Task `override:` | Config `overrides:` |
|--------|-----------------|---------------------|
| Scope | Single task definition | Whole graph under this config |
| Inheritance | Replacement inherits from target | Full substitution (no inheritance) |
| Target | Must exist in base (`uses`) package | Any task in the graph |
| Depth | Top-level tasks only | Any depth, including compound body |



## Config-Level Extensions

Configurations support an `extensions:` section that modifies task
parameters when the config is active.  Unlike overrides (which replace
tasks entirely), extensions augment existing tasks by appending or
prepending to their list-typed parameters or injecting additional
dependencies.

### Appending to a list parameter

```yaml
configs:
  - name: debug
    extensions:
      - task: pkg.build
        with:
          args: { append: ["-debug_access+all", "-kdb"] }
```

### Prepending to a list parameter

```yaml
configs:
  - name: debug
    extensions:
      - task: pkg.build
        with:
          args: { prepend: ["-g"] }
```

### Injecting dependencies

```yaml
configs:
  - name: debug
    extensions:
      - task: pkg.build
        needs: [pkg.setup_debug]
```

### Inline append on derived tasks

The same `append`/`prepend` syntax works inside any task's `with:`
block, not only in config extensions:

```yaml
tasks:
  - name: my_build
    uses: hdlsim.vcs.SimImage
    with:
      args: { append: ["-kdb"] }
```

### Accumulation

Multiple layers can append/prepend to the same parameter.  The values
accumulate in declaration order:

```
base task:     args = ["-O2"]
derived task:  args: { append: ["-Wall"] }   =>  ["-O2", "-Wall"]
config ext:    args: { append: ["-kdb"] }    =>  ["-O2", "-Wall", "-kdb"]
```

If any layer uses a plain value (full replacement), it resets the
accumulated list.  Subsequent appends continue from the new base.

### Extensions vs overrides

| Aspect | Config `extensions:` | Config `overrides:` |
|--------|---------------------|---------------------|
| Effect | Modify parameters | Replace entire task |
| Scope | Single parameter | Whole task |
| Use case | Add debug flags | Stub out expensive tasks |
| Inheritance | Composes across config chain | Last writer wins |

## Importing Configurations
Configurations can be applied to packages when they are imported. For example:

```
package:
  name: p1
  imports:
  - path: 'file/flow.yaml'
    config: cfg1
    with:
      v1: val1
```

In this case, the process above is applied to the package defined in flow.yaml. 

## Implementation
This section summarizes the implementation approach and required code changes to support the specification above.

### Overview of Current Structures
- PackageDef already models: name, imports, uses (base package), params (with), tasks, types, fragments, configs (list of ConfigDef)
- ConfigDef currently provides: name, params (with), uses, overrides, extensions. Missing per spec: imports, fragments, tasks, types.
- FragmentDef supports: tasks, imports, fragments (chaining), types.
- PackageImportSpec currently supports only path (from) and alias (as); per spec we need config selection and parameter overrides on import.

### Data Model Changes
1. PackageImportSpec: add fields
   - config: Optional[str]
   - params: Dict[str,Any] (alias 'with') to carry parameter overrides applied when importing the target package.
2. ConfigDef: add fields
   - imports: List[Union[str,PackageImportSpec]]
   - fragments: List[str]
   - tasks: List[TaskDef]
   - types: List[TypeDef]
3. (Optional) Support specifying 'srcdir' builtin variable (already implied) ensure loader seeds it (rootdir done; add srcdir if not present).

### Loader / Processing Sequence Additions
Adjust PackageProviderYaml/Toml and PackageLoader to implement the staged load sequence:
1. Load package-level imports
   - Evaluate import paths with only builtin/env variables (rootdir, srcdir, env) before package params resolved.
   - Apply import-time config/with overrides when loading each imported package (recursive call providing param overrides and config name).
2. Resolve package inheritance (uses)
   - Merge params: inner (base) then outer (current), then CLI overrides (existing param_overrides logic) maintaining precedence chain.
3. Load package-level fragments in declaration order
   - Allow fragment paths to reference any variables defined so far.
4. Select active config
   - Determine config name: explicit argument to loader (eg PackageLoader.load(path, config=...)), import-specified config, or default rules.
5. Apply configuration
   - If config has imports: load them now (same constraints as package-level config imports: only previously-defined vars in import paths).
   - Resolve config inheritance (uses) merging params into existing variable map; precedence: base-config -> derived-config -> CLI overrides.
   - Load config fragments.
   - Merge config tasks/types/fragments into package namespace; handle overrides (override field) by replacing base definitions while retaining reference links.
6. Elaborate tasks and types
   - Update override resolution logic: when a task/type is overridden in a config, downstream needs/uses links must refer to the most-derived version (already partially handled by PackageLoader._elabTask/_elabType; extend to search config-level definitions before package-level).

### API Adjustments
- PackageLoader.load: add optional parameters config: Optional[str], param_overrides: Dict[str,Any] (already present) to pass selected config.
- When importing a package (PackageImportSpec), propagate its 'config' and 'with' overrides into recursive load calls.

### Override Resolution Logic
- Extend PackageLoader/PackageScope findTask/findType to check config-level definitions first, then package-level, then base package chain.
- When building needs graph (task_graph_builder), ensure overridden tasks replace base tasks in dependency edges.

### Fragment Handling
- For fragments listed in package or config, load them in order; merge tasks/types exactly like package-level lists (append then process overrides).
- Prevent duplicate processing via path stack (PackageLoader.pushPath already supports recursion detection).

### Error Handling & Diagnostics
- Validate specified config exists; if not, suggest similar names.
- If import specifies non-existent config, raise error early.
- Add markers for override targets not found.

### Minimal Code Change Plan
1. Modify package_import_spec.py: add config:str|None, (DONE) params:Dict[str,Any]=Field(alias="with", default_factory=dict)
2. Modify config_def.py: add new fields (imports, fragments, tasks, types) (DONE)
3. Seed builtin 'srcdir' in PackageLoader.__post_init__ (analogous to rootdir).
4. Enhance package_provider_yaml.py to parse new fields.
5. Extend PackageLoader/Provider load sequence with config selection & application (_selectConfig, _applyConfig added) (DONE).
6. Update findTask/findType to consider config-level definitions. (PENDING - current implementation merges tasks/types before load)
7. Update task elaboration (override) to account for config-level overrides before package-level ones. (PARTIAL - override logic added when applying config lists)
8. Add handling of import-level config and with overrides when processing PackageImportSpec. (PENDING - config/with captured but not yet applied during import)
9. Update this documentation (package_config.md) as features are implemented: mark implemented items, add examples for config-level imports/fragments/tasks/types, and note any deviations or additional constraints discovered during coding.

### Future Extensions (Not Immediate)
- Support matrix strategies interacting with config-level params.
- Caching of imported package+config+param combinations.

### Testing Strategy
- Add tests covering:
  - Import with config and parameter overrides.
  - Config inheritance chain merging params.
  - Task override precedence (base package vs package override vs config override).
  - Fragment variable reference resolution order.
  - Default config fallback behavior.
