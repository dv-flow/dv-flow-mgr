# DV Flow Manager Documentation Update Plan

**Date**: 2025-12-24  
**Version**: 1.0

## Executive Summary

This document outlines a comprehensive plan to update the DV Flow Manager documentation to accurately reflect the implemented features. The analysis identified significant gaps between the implementation and documentation, including missing features, incomplete API documentation, and some inconsistencies.

---

## Analysis Summary

### Key Concepts and Features Found in Implementation

#### 1. Core Architecture
- **Package System**: Hierarchical package structure with imports, fragments, and configurations
- **Task System**: Tasks with params, needs, consumes, passthrough, rundir modes
- **Type System**: Custom data types with inheritance (TypeDef, Type classes)
- **Dataflow**: TaskDataItem-based communication between tasks

#### 2. Task Features
- **Task Definition**: TaskDef with YAML schema validation
- **Task Strategies**: 
  - `matrix` for parameterized expansion
  - `generate` for programmatic graph construction
  - `chain` strategy (in StrategyDef but not documented)
- **Task Execution Modes**:
  - Shell scripts (`run` + `shell`)
  - Python tasks (`pytask` + `run`)
  - Inline Python code
  - Compound tasks (`body` or `tasks`)
- **Up-to-date checking**: Custom methods, default checking, `uptodate` parameter
- **Conditional execution**: `iff` parameter with expression evaluation

#### 3. Package Features
- **Package Definitions**: PackageDef with complete YAML schema
- **Package Imports**: Path-based, aliased (`as`), with resolution order
- **Package Fragments**: FragmentDef for splitting large packages
- **Package Configurations**: ConfigDef with extensions, overrides, parameters
- **Package Parameters**: Typed parameters with inheritance
- **Package Overrides**: Parameter overrides for packages
- **Package Extensions**: ExtendDef for modifying tasks

#### 4. Advanced Features
- **PyTask Class-Based API**: `@dc.dataclass class PyTask` with descriptor pattern
- **PyPkg Package Factory**: `PyPkg` class for Python-based package definitions
- **Task Override**: Tasks can override other tasks via `override` field
- **Expression Evaluation**: `${{ }}` syntax with expr_eval.py and expr_parser.py
- **JQ Evaluation**: eval_jq.py for complex data queries
- **Parameter References**: Sophisticated param_ref_eval.py system
- **Name Resolution**: Complex name_resolution.py for package/task lookups

#### 5. CLI Features
- **Commands**: `run`, `show`, `graph`, `util`
- **UI Options**: `log`, `progress`, `tui` output formats
- **Parallel Execution**: `-j` flag for controlling parallelism
- **Force Execution**: `-f/--force` flag
- **Clean Builds**: `--clean` flag
- **Parameter Overrides**: `-D NAME=VALUE` for command-line overrides
- **Configuration Selection**: `-c/--config` for selecting package configs
- **Root Directory**: `--root` for specifying project root

#### 6. Standard Library Tasks (documented but incomplete)
- **std.Message**: Display messages
- **std.FileSet**: Collect files with glob patterns
- **std.CreateFile**: Create files from literal content
- **std.SetEnv**: Set environment variables (with glob expansion support)
- **std.Exec**: Execute shell commands
- **std.SetFileType**: Change fileset types
- **std.IncDirs**: Extract include directories

#### 7. Execution and Monitoring
- **Task Listeners**: Multiple listener types (Log, TUI, Progress, Trace)
- **Trace Output**: Google Event Trace Format (Perfetto compatible)
- **Task Markers**: Error/warning/info markers with file locations
- **Task Memento**: Persistent state for up-to-date checking

#### 8. Rundir Management
- **Rundir Modes**: `unique` vs `inherit` (RundirE enum)
- **Directory Structure**: cache/, log/, and per-task directories
- **Exec Data Files**: JSON files with task execution history

---

## Documentation Gaps and Issues

### Missing Concepts
1. **Task Override Mechanism**: The `override` field in TaskDef is implemented but not documented
2. **PyTask Class API**: New descriptor-pattern API for Python tasks not documented
3. **PyPkg Package Factory**: Python-based package definition mechanism not documented
4. **Package Configurations**: ConfigDef with extensions is implemented but not documented
5. **Package Extensions**: ExtendDef mechanism for modifying tasks not documented
6. **Chain Strategy**: StrategyDef includes `chain` field but never documented
7. **Expression System**: `${{ }}` syntax capabilities not fully documented
8. **JQ Evaluation**: eval_jq.py exists but no documentation
9. **Type System**: Custom types with inheritance barely documented
10. **CLI UI Options**: `tui` and `progress` modes not documented
11. **Trace Format**: Perfetto trace output mentioned but details missing
12. **Task Feeds**: `feeds` field in TaskDef (inverse of needs) not documented

### Incomplete Documentation
1. **std library tasks**: Only 2 of 7 tasks documented in stdlib.rst
2. **TaskRunCtxt API**: Mentioned but incomplete methods
3. **TaskGenCtxt API**: Mentioned but missing many methods
4. **UpToDateCtxt API**: Basic but missing examples
5. **Parameter types**: Complex types (map, list) not fully explained
6. **Consumes/Passthrough patterns**: Pattern matching syntax not documented
7. **Rundir modes**: `inherit` vs `unique` implications not explained
8. **Package resolution**: Full resolution algorithm not documented

### Incorrect/Outdated Documentation
1. **pytask field**: Marked as "deprecated" in code but still documented as primary
2. **uses vs type**: Quickstart uses `type:` field but docs use `uses:` - inconsistent
3. **body vs tasks**: Both are valid but relationship not clear

---

## Implementation Plan

### Phase 1: Core Concept Updates (High Priority)

#### 1.1 Update `userguide/fundamentals.rst`
- Add section on **Task Override** mechanism
- Expand **Types** section with inheritance examples
- Add **Expression System** section explaining `${{ }}` syntax
- Document **feeds** as inverse of **needs**

#### 1.2 Update `userguide/tasks_using.rst`
- Add **Task Override** section with examples
- Expand **Consumes/Passthrough** section with pattern matching
- Add **Rundir Modes** section explaining unique vs inherit
- Add section on **uses vs type** distinction

#### 1.3 Update `userguide/tasks_developing.rst`
- Add **PyTask Class-Based API** section with full examples
- Document **PyPkg Package Factory** pattern
- Add **Chain Strategy** section if implemented
- Clarify inline vs external pytask distinction

#### 1.4 Update `userguide/packages.rst`
- Add **Package Configurations** section (ConfigDef)
- Add **Package Extensions** section (ExtendDef)
- Document parameter overrides
- Clarify package resolution algorithm

#### 1.5 Update `userguide/stdlib.rst`
- Complete documentation for all 7 std library tasks:
  - std.Exec (with examples)
  - std.SetEnv (with glob expansion)
  - std.SetFileType
  - std.IncDirs
- Add examples for each task

### Phase 2: API Reference Updates (High Priority)

#### 2.1 Update `pytask_api.rst`
- Complete **TaskRunCtxt** API documentation
- Complete **TaskGenCtxt** API documentation
- Add **PyTask class** API reference
- Add **PyPkg class** API reference
- Expand **UpToDateCtxt** with more examples

#### 2.2 Create new `types_api.rst`
- Document Type system
- TypeDef schema
- Type inheritance
- Custom type creation

### Phase 3: CLI and Tools Updates (Medium Priority)

#### 3.1 Update `cmdref.rst`
- Document UI options (`-u/--ui`: log, progress, tui)
- Document trace output format and Perfetto integration
- Add examples of common command patterns
- Document `util` command

#### 3.2 Update `incremental.rst`
- Expand custom up-to-date examples
- Document memento system
- Explain exec.json structure

### Phase 4: Advanced Topics (Medium Priority)

#### 4.1 Create `userguide/expressions.rst`
- Document `${{ }}` expression syntax
- Parameter references
- Expression evaluation contexts
- JQ integration (if stable)

#### 4.2 Create `userguide/advanced_features.rst`
- Task override patterns
- Dynamic task generation
- Complex dataflow patterns
- Performance optimization

### Phase 5: Examples and Tutorials (Lower Priority)

#### 5.1 Expand `quickstart.rst`
- Add more complete examples
- Show common patterns
- Link to advanced topics

#### 5.2 Create `examples/` directory
- Real-world flow examples
- Plugin package examples
- Testing patterns

---

## Corrections Needed

1. **Quickstart**: Change `type:` to `uses:` for consistency, or explain both
2. **pytask deprecation**: Clarify status - remove deprecation note or provide migration path
3. **body vs tasks**: Clarify that both are valid (tasks is alias for body)
4. **Parameter resolution**: Document complete precedence order including -D overrides

---

## New Sections Needed

1. `userguide/types.rst` - Type system documentation
2. `userguide/expressions.rst` - Expression evaluation
3. `userguide/configurations.rst` - Package configuration system
4. `reference/schema.rst` - Complete YAML schema reference
5. `reference/cli.rst` - Complete CLI reference with all options

---

## Priority Summary

**Phase 1 (High Priority)**: Core concepts that users need immediately
- Task mechanics, package structure, standard library

**Phase 2 (High Priority)**: API reference for developers
- Complete Python APIs for task development

**Phase 3 (Medium Priority)**: CLI and tooling
- Command-line usage, monitoring, debugging

**Phase 4 (Medium Priority)**: Advanced features
- Expression system, configurations, optimizations

**Phase 5 (Lower Priority)**: Examples and tutorials
- Real-world usage patterns and examples

---

## Success Criteria

- All implemented features are documented
- No incorrect or outdated information remains
- API references are complete with examples
- Standard library tasks are fully documented
- Users can find information about any feature they encounter in code
