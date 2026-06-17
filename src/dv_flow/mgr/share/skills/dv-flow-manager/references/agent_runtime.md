# Agent Runtime & Library Skills

## Discovering and reusing library skills (do this first)

Installed plugin packages can ship reusable **agent skills** — DataSet types
tagged with `std.AgentSkillTag`, each carrying documentation. Before authoring
anything, find what is available and reuse it. **When a library skill fits the
user's goal, suggest it** rather than building something custom.

```bash
dfm show skills                  # list all available skills
dfm show skills --search uvm     # search by keyword (name, desc, skill_doc)
dfm show skills <name>           # show one skill's full documentation
```

Also discover reusable **tasks**:

```bash
dfm show tasks --search sim                                  # by keyword
dfm show tasks --produces "type=std.FileSet,filetype=verilog" --json   # by output
dfm show task <name> --json                                 # inspect one task
dfm context --json                                          # everything at once
```

Related agent-resource tags you may encounter: `std.AgentPersonaTag`,
`std.AgentToolTag`, `std.AgentReferenceTag`. Compose these (and skills) into an
assistant invocation with `dfm agent <tasks...>`.

## Reuse checklist

1. `dfm show skills` / `--search` — is there a skill for this domain?
2. `dfm show tasks --search` / `--produces` — is there a task that already does
   it, or produces what you need?
3. If yes → compose it via `needs` / `uses` (and tell the user).
4. If no → author a task, preferring a typed task over raw shell.

## Running `dfm` inside a std.Agent task

When `dfm` runs inside an LLM-driven `std.Agent` task, the environment variable
`DFM_SERVER_SOCKET` is set, and `dfm` automatically connects to the **parent
DFM session** over a Unix socket (client mode). The usual commands work:

```bash
dfm run task1 task2       # execute via the parent session
dfm show tasks            # query available tasks
dfm context --json        # project context
dfm validate              # validate configuration
```

### Why server mode matters

- **Resource sharing** — respects the parent's parallelism limit (`-j`).
- **State consistency** — sees outputs of tasks already completed.
- **Cache sharing** — uses the same memento cache for incremental builds.
- **Unified logging** — output appears in the parent session's logs.

### Example: build something the agent generated

```bash
# 1. write a source file
cat > counter.sv <<'EOF'
module counter(input clk, rst_n, output logic [7:0] count);
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) count <= 0; else count <= count + 1;
endmodule
EOF

# 2. build it via the parent session (returns JSON when in client mode)
dfm run build
# -> {"status": 0, "outputs": [...], "markers": []}
```

A non-zero `status` (or entries in `markers`) indicates errors to fix.
