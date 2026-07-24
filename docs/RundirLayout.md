
rundir/
  - info/
    - task-execution database
    - execution logs
  - tasks/
    - per-task execution directory
    - only for tasks that require persistent outputs
  - bin/
    - `dfm-out` / `dfm` shims that re-invoke the current interpreter, so shell
      tasks reach them on PATH without the console scripts being installed
  - out/
    - per-run output-data directories, one per run-id, populated by `std.Publish`
      (and `dfm-out publish`)
    - `<run-id>/` (e.g. `0001`, `0002`, ...) — this run's deliverables
      - `.dfm-publish.json` — provenance manifest (dest → src task, sha256, size)
    - `latest` → symlink to the most recent `<run-id>`

