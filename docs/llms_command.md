# The `dfm llms` Command

## Overview

The `dfm llms` command outputs comprehensive context information about DV Flow Manager specifically formatted for Large Language Models (LLMs). This enables AI assistants like GitHub Copilot CLI, Claude, or ChatGPT to provide accurate, context-aware help with DV Flow Manager workflows.

## Purpose

When working with AI assistants on DV Flow Manager projects, the assistant needs to understand:
- Core concepts (tasks, packages, dataflow, types)
- Available commands and their syntax
- Common usage patterns
- File structure and organization
- Integration points

The `llms` command provides this context in a single, concise output.

## Usage

```bash
# Display LLM context
dfm llms

# Pipe to your preferred AI assistant
dfm llms | gh copilot chat
```

## Output Content

The command outputs a markdown-formatted document containing:

1. **Core Concepts**
   - Tasks and task types
   - Packages and parameterization
   - Dataflow and data items
   - Types and custom data structures
   - Tags for metadata
   - Visibility scopes
   - Expression evaluation

2. **Key Features**
   - Incremental execution
   - Parallel processing
   - Task visibility control
   - Type-based tagging
   - Conditional execution
   - And more...

3. **Command Reference**
   - `run` - Execute tasks
   - `show` - Display task information
   - `graph` - Generate dependency visualizations
   - `llms` - Output context for AI

4. **Common Use Cases**
   - HDL simulation workflows
   - Verification flows
   - Synthesis pipelines
   - AI-assisted code generation

5. **Documentation Structure**
   - Links to relevant documentation files
   - Quick reference to key concepts

## Implementation

The command searches for `llms.txt` in two locations:

1. **Package share directory**: `<pkg_install>/share/llms.txt`
   - Installed version from the package
   - Always available after installation

2. **Project root**: Walks up from current directory
   - Allows project-specific customization
   - Overrides package version if present

## Integration with AI Assistants

### GitHub Copilot CLI

```bash
# One-time context load
dfm llms | gh copilot chat

# Or create an alias
alias dfm-ai='dfm llms | gh copilot chat'
```

### ChatGPT / Claude (Copy-paste)

```bash
# Copy the output
dfm llms | pbcopy  # macOS
dfm llms | xclip -selection clipboard  # Linux
dfm llms | clip  # Windows
```

Then paste into your AI assistant conversation.

### Custom AI Workflows

```bash
# Include in prompts
CONTEXT=$(dfm llms)
echo "$CONTEXT" | your-ai-tool --prompt "Help me create a task that..."
```

## Customizing Context

To customize the context for your project:

1. Create a `llms.txt` file in your project root
2. Include project-specific information
3. Reference the base context or extend it

Example project-specific `llms.txt`:

```markdown
# Project: MyChip Verification

This project uses DV Flow Manager for RTL verification.

## Project Structure
- src/rtl/: RTL source files
- tests/: Verification tests
- flow.yaml: Main flow definition

## Custom Tasks
- build_rtl: Compile RTL with Verilator
- run_smoke: Run smoke tests
- run_regression: Full regression suite

## Package Dependencies
- hdlsim: For Verilator integration
- custom_checkers: In-house verification checkers

[Include standard DV Flow Manager context below...]
```

## Source Location

The canonical `llms.txt` file is maintained at:
- `src/dv_flow/mgr/share/llms.txt` (source)
- Installed to package share directory on `pip install`

## Updates

The `llms.txt` content is updated with each DV Flow Manager release to reflect:
- New features and capabilities
- Command syntax changes
- Best practices evolution
- Documentation structure changes

## Related Commands

- `dfm show`: Get detailed information about specific tasks
- `dfm graph`: Visualize task dependencies
- `dfm run --help`: Get command-specific help

## Why This Matters

Without proper context, AI assistants may:
- Suggest incorrect syntax or non-existent features
- Miss DV Flow Manager-specific patterns
- Provide generic build system advice

With `dfm llms` context, AI assistants can:
- Understand DV Flow Manager's unique dataflow model
- Suggest appropriate standard library tasks
- Help with package organization
- Debug flow definition issues
- Propose best practices specific to DV Flow Manager

## Example Session

```bash
$ dfm llms | gh copilot chat
? What would you like to do?
> I need to create a task that compiles SystemVerilog files with Verilator

GitHub Copilot: Based on the DV Flow Manager context, you should use the 
hdlsim plugin. Here's an example:

```yaml
tasks:
  - name: rtl_files
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: src/rtl
      include: "*.sv"
  
  - name: compile
    uses: hdlsim.vlt.SimImage
    needs: [rtl_files]
    with:
      top: [my_top_module]
```

This uses the FileSet task to collect your sources, then passes them
to Verilator via the hdlsim package's SimImage task.
```

## Best Practices

1. **Load context at session start**: Paste or pipe once per conversation
2. **Update periodically**: Re-run if switching projects or after upgrades
3. **Supplement with specifics**: Add project context as needed
4. **Verify suggestions**: AI assistance is helpful but always review generated code
5. **Report issues**: If AI consistently misunderstands features, the context may need updating
