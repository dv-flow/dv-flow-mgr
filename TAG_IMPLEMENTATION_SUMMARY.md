# Type-Based Tags Implementation Summary

## Overview
Implemented type-based tags for tasks and packages where tags are DataType instances (must derive from std.Tag). Tags support parameter inheritance and variable reference expansion, aligned with how task parameters are processed.

## Key Design Decisions

### Schema (Option 2 - Inline Parameter Override)
```yaml
tags:
  - mypkg.Tag                    # Simple type reference (uses all defaults)
  - mypkg.Tag: {val1: "a"}       # Type reference with parameter overrides
```

### Type System Alignment
- **Before**: Types used eager parameter evaluation (`paramT` only)
- **After**: Types now use both:
  - `param_defs`: ParamDefCollection for deferred evaluation (like tasks)
  - `paramT`: Pydantic model for backward compatibility and eager access

This alignment ensures:
1. Consistent parameter processing between tasks and types
2. Proper handling of `uses` inheritance chains
3. Support for variable reference expansion (`${{...}}`)
4. Lazy evaluation capabilities when needed

## Implementation Details

### Core Changes

1. **Schema Updates** (`schema/flow.dv.schema.json`):
   - Added `tags` array to `package-def` and `task-def`
   - Tags are `oneOf`: string (type reference) or object (inline overrides)
   - Uses `patternProperties` for flexible key-value parameter syntax

2. **std.Tag Base Type** (`src/dv_flow/mgr/std/flow.dv`):
   ```yaml
   types:
     - name: Tag
       doc: Base type for all tags
       with:
         category:
           type: str
           value: ""
         value:
           type: str
           value: ""
   ```

3. **Data Structures**:
   - `Task.tags`: `List[Type]` - instantiated tag Type objects
   - `Package.tags`: `List[Type]` - instantiated tag Type objects
   - `Type.param_defs`: `ParamDefCollection` - for deferred evaluation

4. **Type Elaboration** (`_elabType`):
   - Now collects `param_defs` using `_collectParamDefs` (like tasks)
   - Still builds `paramT` for backward compatibility
   - Resolves `uses` inheritance chain

5. **Tag Resolution** (`_resolveTags`):
   - Called after types are loaded
   - Resolves type references across packages
   - Validates tags derive from std.Tag
   - Instantiates tag Type objects with merged parameters

6. **Tag Instantiation** (`_instantiateTag`):
   - Walks inheritance chain to collect all parameters
   - Processes in reverse order (base first, derived overrides)
   - Applies user-provided parameter overrides
   - Evaluates variable references (`${{...}}`)
   - Builds both `param_defs` and `paramT`

### Parameter Inheritance Example
```yaml
types:
  - name: BaseTag
    uses: std.Tag
    with:
      category: "base"
      value: "default"
  
  - name: DerivedTag
    uses: test.BaseTag
    with:
      category: "derived"     # Overrides category
      # value inherited from BaseTag

tasks:
  - name: t1
    tags:
      - test.DerivedTag:
          value: "custom"      # Runtime override
    # Final result: category="derived", value="custom"
```

## Test Coverage

### tests/unit/test_tags.py (6 tests):
1. **test_task_no_tags**: Empty tags list default
2. **test_task_simple_tag**: Basic tag reference with defaults
3. **test_tag_parameter_override**: Override parameters at tag usage
4. **test_tag_multiple_on_task**: Multiple tags on single task
5. **test_tag_inheritance**: Tag type inherits from another tag type
6. **test_package_tags_simple**: Tags on packages

All tests verify:
- Type reference resolution
- Parameter inheritance through `uses` chain
- Parameter override merging
- Proper instantiation of Type objects with `paramT`

## Usage Examples

### Basic Tag
```yaml
package:
  name: myproject
  
  types:
    - name: BuildTag
      uses: std.Tag
      with:
        category: "build"
  
  tasks:
    - name: compile
      tags: [myproject.BuildTag]
      run: make
```

### Tag with Parameter Override
```yaml
tasks:
  - name: test
    tags:
      - myproject.BuildTag:
          value: "unit-test"
    run: pytest
```

### Tag Inheritance
```yaml
types:
  - name: SeverityTag
    uses: std.Tag
    with:
      category: "severity"
      value: "info"
  
  - name: ErrorTag
    uses: myproject.SeverityTag
    with:
      value: "error"       # Override default severity
```

### Package Tags
```yaml
package:
  name: myproject
  tags:
    - std.Tag:
        category: "project-type"
        value: "verification"
```

## Benefits

1. **Type Safety**: Tags are typed DataType instances, not free-form strings/dicts
2. **Consistency**: Parameter handling matches task parameter processing
3. **Reusability**: Tag types can be defined once and reused with different parameters
4. **Inheritance**: Tag types support full inheritance chains via `uses`
5. **Flexibility**: Parameters can be overridden at each level (type def, derived type, usage)
6. **Validation**: All tag types must derive from std.Tag (enforced)

## Future Enhancements

Potential areas for extension:
- Tag-based task filtering in CLI (`dv-flow run --tag=category:build`)
- Tag queries in workflow conditions
- Tag-based documentation generation
- Tag validation rules (e.g., required tags, allowed values)
- Tag metadata export for external tools
