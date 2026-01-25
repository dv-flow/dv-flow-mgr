# DV Flow Manager Advanced Patterns

## Task Override Patterns

### Configuration-Based Override

```yaml
package:
  name: my_project
  
  tasks:
    - name: sim
      uses: hdlsim.vlt.SimImage
      with:
        optimization: "O2"
  
  configs:
    - name: debug
      tasks:
        - name: sim_debug
          override: sim
          with:
            optimization: "O0"
            debug: true
    
    - name: fast
      tasks:
        - name: sim_fast
          override: sim
          with:
            optimization: "O0"
            fast_mode: true
```

### Conditional Override

```yaml
tasks:
  - name: sim_linux
    override: sim
    iff: ${{ platform == "linux" }}
    uses: hdlsim.vlt.SimImage
  
  - name: sim_windows
    override: sim
    iff: ${{ platform == "windows" }}
    uses: hdlsim.msvc.SimImage
```

### Layered Configurations

```yaml
configs:
  - name: base_debug
    tasks:
      - name: compile_debug
        override: compile
        with:
          debug: true
  
  - name: instrumented
    uses: base_debug           # Inherit from base_debug
    tasks:
      - name: compile_inst
        override: compile
        with:
          coverage: true
          profiling: true
```

## Complex Dataflow

### Fan-Out/Fan-In

```yaml
tasks:
  # Fan-out: One source to many consumers
  - name: sources
    uses: std.FileSet
    with:
      include: "*.sv"
  
  - name: lint
    uses: linter.Check
    needs: [sources]
  
  - name: compile
    uses: hdlsim.vlt.SimImage
    needs: [sources]
  
  - name: synthesize
    uses: synth.Build
    needs: [sources]
  
  # Fan-in: Collect results
  - name: report
    uses: reports.Summary
    needs: [lint, compile, synthesize]
```

### Selective Dataflow

Filter inputs by type or attributes:

```yaml
tasks:
  - name: all_files
    uses: std.FileSet
    with:
      include: "**/*.sv"
  
  - name: rtl_compile
    uses: hdlsim.vlt.SimImage
    needs: [all_files]
    consumes:
      - type: std.FileSet
        attributes: [rtl]
  
  - name: tb_compile
    uses: hdlsim.vlt.SimImage
    needs: [all_files]
    consumes:
      - type: std.FileSet
        attributes: [testbench]
```

### Data Transformation Pipeline

```yaml
tasks:
  - name: gather
    uses: std.FileSet
    with:
      include: "*.v"
  
  - name: preprocess
    uses: preprocessor.Transform
    needs: [gather]
    passthrough: none          # Don't forward original
  
  - name: compile
    uses: hdlsim.vlt.SimImage
    needs: [preprocess]
    # Receives only preprocessed files
```

## Matrix Strategy

Generate multiple task instances from combinations:

```yaml
tasks:
  - name: test_matrix
    strategy:
      matrix:
        test: [smoke, full, random]
        seed: [100, 200, 300]
    body:
      - name: run
        uses: hdlsim.vlt.SimRun
        with:
          plusargs:
            - "+test=${{ matrix.test }}"
            - "+seed=${{ matrix.seed }}"
```

Results in 9 tasks (3 tests × 3 seeds).

### Exclude Combinations

```yaml
strategy:
  matrix:
    os: [linux, windows, macos]
    compiler: [gcc, clang, msvc]
    exclude:
      - os: windows
        compiler: gcc
      - os: macos
        compiler: msvc
```

## Dynamic Task Generation

### Python Generator

```yaml
tasks:
  - name: dynamic_tests
    strategy:
      generate:
        run: my_pkg.generators.CreateTests
```

```python
# my_pkg/generators.py
def CreateTests(ctxt, input):
    import json
    
    # Read test list from file
    with open(os.path.join(ctxt.srcdir, "tests.json")) as f:
        tests = json.load(f)
    
    for test in tests:
        task = ctxt.mkTaskNode(
            "hdlsim.vlt.SimRun",
            name=ctxt.mkName(f"test_{test['name']}"),
            plusargs=[f"+test={test['name']}"],
            seed=test.get('seed', 0)
        )
        ctxt.addTask(task)
```

### Parameterized Generation

```yaml
tasks:
  - name: parallel_work
    with:
      task_count:
        type: int
        value: 10
    strategy:
      generate:
        run: my_pkg.GenerateParallel
```

```python
def GenerateParallel(ctxt, input):
    count = input.params.task_count
    for i in range(count):
        task = ctxt.mkTaskNode(
            "std.Exec",
            name=ctxt.mkName(f"task_{i}"),
            command=f"./process.sh {i}"
        )
        ctxt.addTask(task)
```

## Package Extensions

Modify imported tasks without replacement:

```yaml
package:
  name: my_project
  
  imports:
    - hdlsim.vlt
  
  configs:
    - name: coverage
      extensions:
        - task: hdlsim.vlt.SimImage
          with:
            coverage:
              type: bool
              value: true
          needs:
            - coverage_setup
```

## Incremental Execution

### Custom Up-to-Date Check

```yaml
tasks:
  - name: generate
    uses: std.Exec
    with:
      command: "./generate.sh"
    uptodate: my_pkg.CheckInputs
```

```python
async def CheckInputs(ctxt):
    import glob
    
    # Get current input files
    inputs = glob.glob(os.path.join(ctxt.srcdir, "*.tmpl"))
    
    # Compare with saved state
    saved = ctxt.memento.get("inputs", [])
    if set(inputs) != set(saved):
        return False
    
    # Check timestamps
    for f in inputs:
        current = os.path.getmtime(f)
        saved_time = ctxt.memento.get(f"mtime_{f}")
        if saved_time != current:
            return False
    
    return True
```

### Timestamp-Based Execution

```yaml
- name: generate
  uses: std.Exec
  with:
    command: "./generate.sh"
    when: changed
    timestamp: "generated/marker.txt"
```

## Resource Management

### License-Limited Parallelism

```bash
# Only 2 synthesis licenses available
dfm run synthesis_jobs -j 2
```

### Memory-Intensive Sequencing

```yaml
tasks:
  - name: big_sim_1
    uses: hdlsim.vlt.SimRun
  
  - name: big_sim_2
    uses: hdlsim.vlt.SimRun
    needs: [big_sim_1]         # Serialize to avoid OOM
```

## Performance Optimization

### Separate Stable and Changing Code

```yaml
tasks:
  # Rarely changing
  - name: third_party
    uses: std.FileSet
    with:
      base: external
      include: "**/*.sv"
  
  # Frequently changing
  - name: project
    uses: std.FileSet
    with:
      base: src
      include: "**/*.sv"
  
  # Compile independently
  - name: lib_compile
    uses: hdlsim.vlt.Compile
    needs: [third_party]
  
  - name: src_compile
    uses: hdlsim.vlt.Compile
    needs: [project]
  
  # Link together
  - name: link
    uses: hdlsim.vlt.Link
    needs: [lib_compile, src_compile]
```

### Parallel File Processing

```yaml
tasks:
  - name: process_files
    strategy:
      matrix:
        file: ["a.v", "b.v", "c.v", "d.v"]
    body:
      - name: process
        uses: std.Exec
        with:
          command: "./process.sh ${{ matrix.file }}"
```

## Debugging Flows

### Generate and View Graph

```bash
dfm graph my_task -o debug.dot
dot -Tpng debug.dot -o debug.png
```

### Isolate Problem Task

```bash
# Force single task execution with logging
dfm run problem_task -f -j 1 -u log
```

### Analyze Traces

1. Run flow (traces auto-generated)
2. Open `rundir/log/<task>.trace.json` in Perfetto
3. Identify:
   - Longest tasks
   - Idle time
   - Critical path
   - Parallel efficiency

## Common Integration Patterns

### CI/CD Pipeline

```yaml
package:
  name: project
  
  configs:
    - name: ci
      with:
        parallel_tests: 4
        coverage: true
  
  tasks:
    - name: ci_flow
      body:
        - name: build
          uses: hdlsim.vlt.SimImage
        - name: test
          uses: test.Runner
          needs: [build]
        - name: coverage_report
          uses: coverage.Report
          needs: [test]
          iff: ${{ coverage }}
```

```bash
dfm run ci_flow -c ci -u log --clean
```

### Multi-Configuration Build

```yaml
configs:
  - name: verilator
    overrides:
      - override: hdlsim
        with: hdlsim.vlt
  
  - name: xcelium
    overrides:
      - override: hdlsim
        with: hdlsim.xcelium
  
  - name: vcs
    overrides:
      - override: hdlsim
        with: hdlsim.vcs
```

```bash
dfm run sim -c verilator
dfm run sim -c xcelium
dfm run sim -c vcs
```

### Regression Suite

```yaml
tasks:
  - name: regression
    strategy:
      matrix:
        test: [test1, test2, test3, ..., test100]
        seed: [1, 2, 3, 4, 5]
    body:
      - name: run
        uses: hdlsim.vlt.SimRun
        with:
          test: ${{ matrix.test }}
          seed: ${{ matrix.seed }}
  
  - name: collect_results
    uses: regression.Collect
    needs: [regression]
```

```bash
# Run full regression with 16 parallel jobs
dfm run collect_results -j 16
```
