# Rundir layout

What `dfm run` writes, as the code does it today. `rundir` is `./rundir` in
the directory `dfm run` is invoked from.

```
rundir/
  <task>/                      # one directory per task (the legacy naming scheme)
    <task>.exec_data.json      #   what ran: params, inputs, commands, result, output
    <task>.log                 #   the task's log
    <task>_cmd.sh              #   a shell task's script
    ...                        #   whatever the task writes
  <compound>/<subtask>/        # a compound's subtasks nest under it
  log/
    <package>.trace.json       # execution trace of the last run
  bin/
    dfm-out, dfm               # shims that re-invoke this interpreter, put on
                               # PATH for shell tasks
  out/
    <run-id>/                  # one per run (YYYYMMDD-HHMMSS[-N], or --run-id)
      results.json             #   the run record (dvflow-results/1)
      summary.md               #   the record as markdown
      junit.xml, ctrf.json     #   when results.formats asks for them
      results/                 #   the record as a link tree (results.tree)
        FAILED/                #     links to every failure (only when there are any)
        <root>/<child>/...     #     one dir per result: STATUS, log, and links
                               #     to the task's rundir entries
      logs/                    #   copies of the logs (results.copy_logs)
      .dfm-publish.json        #   std.Publish provenance manifest, when the run publishes
      ...                      #   std.Publish / `dfm-out publish` deliverables
    latest -> <run-id>         # the newest run
```

Notes:

- Task directories are reused from run to run; that is what makes up-to-date
  checks work. A record's artifacts link into them, so an old record's log or
  waves may have been overwritten since: readers compare the mtime/size stamped
  in `results.json` and show such a file as stale (see
  `docs/reference/results.rst`).
- `DV_FLOW_RUNDIR_LAYOUT` selects the naming scheme for task files (`legacy`
  is the default and is what is shown above).
- The current run and the one before it are kept (`results.keep_previous:
  1`; `all` never prunes); an explicit `--run-id` directory is never pruned.
- `out/<run-id>/` is created before the first task runs and exported to tasks
  as `$DFM_OUT_DIR` (with `$DFM_RUN_ID`).
- Older versions used zero-padded counters (`0001`) for run-ids; those
  directories are still recognized.
