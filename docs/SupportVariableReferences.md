
Parameters can be declared at two levels of a dv-flow description.
- Packages may declare variables
- Tasks may declare variables

Parameters may be referenced in several places:
- When specifying the value of package parameters
- When specifying the value of task variables
- When specifying the condition (iff) under which a task executes

Variables are referenced using ${{ <varname> }} syntax. 
Expressions involving variables are evaluated by the tool during
the graph-building process implemented in task_graph_builder.py

Variable references use a scoped scheme.
- Variables declared in the current package
- Variable declared in the enclosing compound-task scopes of the current task scope
- Variables declared in the current task scope
  - Variables declared in the enclosing compound-task scope are also visible via a 'this' reference
- Full references to package variables. 

Must update task_graph_builder.py to maintain a stack of these stacks. Structure
this as a stack of name-resolution contexts. Each name-resolution context
should have:
  - A handle back to the task_graph_builder to resolve package-qualified references
  - A handle to the current package
  - A stack of task name-resolution scopes. These scopes should have:
    - A handle to the active task
    - A 'dict' of string to object for synthetic variables
The multiple levels is needed because we will setup a new scope when 
switching to working in a different package.

- When creating as TaskNode (mkTaskNode)
  - Identify the package in which the task is declared
  - Create a new name-resolution scope with a handle to 'self' and to the package
  - Push the new name-resolution on the stack
  - Call _mkTaskNode to construct the node
  - Pop the new name-resolution scope from the stack

- When building a compound task, do the following when building a sub-task
  - Push a new task scope onto the name-resolution scope
  - Add a reference named 'this' to the `paramT` field of the
    compound task being constructed
  - Construct the task
  - Pop the task scope from the name-resolution scope

Variables are expanded in _expandParams. Update this to use the name resolution stack.
- Package parameters are stored in the `paramsT` object within the package.
  You can check for the existence of the variable using hasattr
- Task parameters are stored in the `paramsT` object within the task.
  You can check for the existence of the variable using hasattr
- Look for the package name in hierarchical references in the _pkg_m dict.


