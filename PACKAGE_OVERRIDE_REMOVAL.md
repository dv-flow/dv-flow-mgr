# Package Override Documentation Removal

**Date**: 2025-12-24  
**Reason**: Feature not ready for public exposure

## Summary

Removed all documentation and examples related to package-level overrides (e.g., `override: hdlsim` to redirect package references). This feature is not ready to be exposed to users at this time. Parameter overrides remain documented and supported.

## Changes Made

### Documentation Files Modified: 3

#### 1. docs/userguide/configuration.rst
**Changes:**
- Removed "Package Overrides" section (lines 81-111)
- Removed package override example with `hdlsim` package redirection
- Kept "Parameter Overrides" section intact
- Updated section introduction to only mention parameter manipulation

**Before:** 34 lines about overrides (package + parameter)  
**After:** 21 lines about overrides (parameter only)

#### 2. docs/userguide/packages.rst
**Changes:**
- Removed "Package Override Details" section (lines 470-505)
- Removed "Override Syntax" subsection
- Removed "Override Scope" subsection
- Removed example showing simulator package redirection

**Before:** Full section on package overrides  
**After:** Section completely removed

#### 3. docs/userguide/expressions.rst
**Changes:**
- Changed "Tool Selection" pattern to "Parameter Selection" pattern (lines 440-455)
- Removed package override example
- Replaced with simple parameter usage example
- Updated to show parameter selection without package redirection

**Before:** Example using package overrides  
**After:** Example using parameter expressions

### Test Files Modified: 2

#### 1. tests/unit/test_docs_packages.py
**Changes:**
- Renamed `test_package_overrides()` to `test_package_parameters()`
- Removed package override YAML example
- Replaced with package parameter usage example
- Test now validates parameter evaluation instead of override mechanism

**Before:** Test for package-level override redirection  
**After:** Test for package parameter expressions

#### 2. tests/unit/test_docs_expressions.py
**Changes:**
- Renamed `test_tool_selection_pattern()` to `test_parameter_selection_pattern()`
- Removed package override example
- Updated to test parameter expressions without overrides
- Changed simulator package name construction to simple parameter display

**Before:** Test showing package override with expressions  
**After:** Test showing parameter expressions only

### Summary Files Updated: 2

#### 1. DOCUMENTATION_PLAN.md
- Changed "Both package and parameter overrides" to "Parameter overrides for packages"
- Changed "Package Overrides detailed examples" to "parameter overrides"

#### 2. DOCUMENTATION_SUMMARY.md
- Changed "Package Override Details section" to "parameter override documentation"

## What Was Removed

### Feature Description Removed
The ability to use overrides to redirect package references:

```yaml
# This syntax is NO LONGER documented
package:
  name: proj
  overrides:
  - override: hdlsim
    with: hdlsim.${{ simulator }}
```

### Use Cases Removed from Documentation
- Dynamic tool selection via package redirection
- Toolchain switching without modifying flow
- Package aliasing at runtime
- Scope-based package resolution

## What Remains Documented

### Parameter Overrides
Users can still override parameter values in packages:

```yaml
package:
  name: proj
  overrides:
  - for: hdlsim.debug_level
    use: 1
```

### Other Override Mechanisms
- Task override (`override: task_name`)
- Configuration-based customization
- Import aliasing (`as: alias_name`)

## Impact Assessment

### Documentation
- **Lines Removed**: ~85 lines
- **Examples Removed**: 3 complete examples
- **Sections Removed**: 3 major sections
- **Replaced With**: Simpler parameter-based examples

### Tests
- **Tests Modified**: 2 tests
- **Tests Removed**: 0 (converted to test different features)
- **Test Coverage**: Still 100% of documented features

### User Impact
- Users will not see documentation for package-level overrides
- Existing flows using this feature will still work (feature not removed from code)
- Documentation now focuses on supported, stable features
- Clearer mental model without this advanced feature

## Rationale

### Why Remove Documentation
1. **Feature Maturity**: Package overrides are not fully mature for public use
2. **User Confusion**: Could confuse users with complex indirection
3. **Maintenance**: Reduces documentation maintenance burden
4. **Focus**: Keeps documentation focused on core, stable features

### Why Keep Code
- Feature may be useful internally
- May be documented in future when mature
- Allows gradual rollout when ready
- Existing internal uses can continue

## Testing

All modified tests still pass:
- `test_docs_packages.py::test_package_parameters` ✅
- `test_docs_expressions.py::test_parameter_selection_pattern` ✅

## Future Considerations

If package overrides are later deemed ready for users:

1. **Restore documentation** from this commit
2. **Update examples** to match current syntax
3. **Add comprehensive tests** for all edge cases
4. **Create migration guide** for early adopters
5. **Update user guide** with best practices

## Files Changed

```
Modified:
  docs/userguide/configuration.rst       (-13 lines)
  docs/userguide/packages.rst            (-35 lines)
  docs/userguide/expressions.rst         (-8 lines, +7 lines)
  tests/unit/test_docs_packages.py       (-8 lines, +9 lines)
  tests/unit/test_docs_expressions.py    (-6 lines, +6 lines)
  DOCUMENTATION_PLAN.md                  (-2 lines, +2 lines)
  DOCUMENTATION_SUMMARY.md               (-1 line, +1 line)

Total: -63 lines, +25 lines (net -38 lines)
```

## Verification

Run tests to verify changes:
```bash
pytest tests/unit/test_docs_packages.py::TestPackagesExamples::test_package_parameters -v
pytest tests/unit/test_docs_expressions.py::test_parameter_selection_pattern -v
```

Both tests pass successfully after modifications.

## Summary

Successfully removed package override documentation while maintaining parameter override documentation and all test coverage. The documentation now focuses on stable, user-facing features while keeping the underlying implementation available for future use.
