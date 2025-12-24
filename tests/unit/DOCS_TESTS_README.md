# Documentation Examples Test Suite

This directory contains comprehensive unit tests for all code examples in the DV Flow Manager documentation.

## Test Organization

Tests are organized by documentation file:

- `test_docs_fundamentals.py` - Tests for `userguide/fundamentals.rst`
- `test_docs_tasks_using.py` - Tests for `userguide/tasks_using.rst`
- `test_docs_tasks_developing.py` - Tests for `userguide/tasks_developing.rst`
- `test_docs_packages.py` - Tests for `userguide/packages.rst`
- `test_docs_stdlib.py` - Tests for `userguide/stdlib.rst`
- `test_docs_expressions.py` - Tests for `userguide/expressions.rst`
- `test_docs_advanced_features.py` - Tests for `userguide/advanced_features.rst`
- `test_docs_incremental.py` - Tests for `incremental.rst`

## Running Tests

Run all documentation example tests:

```bash
pytest tests/unit/test_docs_*.py -v
```

Run tests for a specific documentation file:

```bash
pytest tests/unit/test_docs_fundamentals.py -v
```

Run a specific test:

```bash
pytest tests/unit/test_docs_fundamentals.py::TestFundamentalsExamples::test_basic_task_with_uses -v
```

## Test Coverage

### Fundamentals (userguide/fundamentals.rst)
- ✅ Basic task with uses and parameters
- ✅ Dataflow with FileSet and needs
- ✅ Custom type definitions
- ✅ Type inheritance
- ✅ Expression syntax
- ✅ Feeds relationship
- ✅ Complete flow execution

### Tasks Using (userguide/tasks_using.rst)
- ✅ Conditional tasks with iff
- ✅ Task override mechanism
- ✅ Consumes pattern matching
- ✅ Passthrough modes
- ✅ Rundir unique mode
- ✅ Rundir inherit mode
- ✅ DataItem tasks
- ✅ Compound task execution

### Tasks Developing (userguide/tasks_developing.rst)
- ✅ Inline pytask implementation
- ✅ Matrix strategy
- ✅ PyTask class definition
- ✅ External pytask execution
- ✅ Generate strategy
- ✅ Programmatic graph generation

### Packages (userguide/packages.rst)
- ✅ Minimal package definition
- ✅ Package imports by path
- ✅ Package imports with alias
- ✅ Package parameters
- ✅ Package fragments
- ✅ Package configurations
- ✅ Package extensions
- ✅ Package overrides
- ✅ Multi-package flows

### Standard Library (userguide/stdlib.rst)
- ✅ std.FileSet example
- ✅ std.CreateFile example
- ✅ std.Exec example
- ✅ std.SetEnv example
- ✅ std.SetEnv with glob expansion
- ✅ std.SetFileType example
- ✅ std.IncDirs example
- ✅ std.Message example
- ✅ std.Message with expressions
- ✅ Complete stdlib workflow

### Expressions (userguide/expressions.rst)
- ✅ Basic parameter reference
- ✅ Arithmetic operations
- ✅ Boolean expressions
- ✅ String concatenation
- ✅ Matrix variables
- ✅ Conditional expressions
- ✅ List element access
- ✅ Dictionary value access
- ✅ Version construction pattern
- ✅ Path construction pattern
- ✅ Conditional features pattern
- ✅ Tool selection pattern

### Advanced Features (userguide/advanced_features.rst)
- ✅ Selective override
- ✅ Layered overrides
- ✅ Conditional override
- ✅ Fan-out/fan-in dataflow
- ✅ Selective dataflow
- ✅ Programmatic generation
- ✅ Parameterized generation
- ✅ Dependency management
- ✅ Data transformation pipeline

### Incremental Builds (incremental.rst)
- ✅ Memento creation
- ✅ Up-to-date check
- ✅ Content hash pattern
- ✅ Dependency tracking pattern
- ✅ Exec.json structure

## Test Statistics

- **Total Test Files**: 8
- **Total Test Classes**: 11
- **Total Test Functions**: ~70+
- **Code Examples Tested**: ~80+
- **Documentation Pages Covered**: 8

## Test Patterns

### Unit Tests
Most tests verify that:
1. YAML parses correctly
2. Packages load without errors
3. Task graphs build successfully
4. Types are resolved correctly

### Integration Tests (marked with @pytest.mark.asyncio)
These tests verify:
1. Tasks execute successfully
2. Dataflow works correctly
3. Listeners receive proper events
4. Exit status is correct

### System Tests
Tests involving:
1. File I/O operations
2. External process execution
3. Directory structure creation
4. Multi-package interactions

## Extending Tests

To add tests for new documentation examples:

1. Create test file: `test_docs_<section>.py`
2. Add test class: `class Test<Section>Examples`
3. Add test methods for each example
4. Use existing patterns for consistency
5. Mark async tests with `@pytest.mark.asyncio`
6. Clean up with tmpdir fixture

Example:

```python
class TestNewSectionExamples:
    def test_example_name(self, tmpdir):
        """Test description"""
        flowdv = """
package:
  name: test
  tasks:
  - name: task1
    uses: std.Message
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
```

## Continuous Integration

These tests should be run:
- Before merging documentation updates
- After any API changes
- As part of release verification
- On a regular schedule (nightly)

## Maintenance

When updating documentation:
1. Update or add corresponding tests
2. Run tests to verify examples work
3. Update this README if test structure changes
4. Keep test coverage above 95% of examples

## Known Limitations

Some features that cannot be fully tested in unit tests:
- TUI mode (requires terminal)
- Perfetto trace viewing (requires browser)
- Distributed execution (requires cluster)
- Some CLI options (tested separately in system tests)

These are covered by:
- Manual testing procedures
- System/integration tests
- End-to-end testing

## Contact

For questions about tests or to report test failures, contact the development team.
