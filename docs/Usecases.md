
# Simple Initial Project Setup


# Reconfigure Project Build

# Global Configuration Data
Some configuration data is global in nature -- in other words,
it is relevant to multiple tools. Debug is one example. Enabling
a debug flow impacts multiple simulation tools, and may impact
how user-specified input behaves as well (eg adding +UVM_VERBOSITY)

# Configure Package Usage
I have a package that depends on UVM, as well as other packages (UVCs)
that depend on UVM. By default, the UVM library is provided as a
pre-compiled library (n simulators that support it). For "reasons",
I want to switch to using the pure-source version. My choice must
apply to all packages within my orbit -- in other words, having
my package depend on source UVM while the UVC depends on pre-compiled
will result in a conflict.

# Configure Project Toolchain
My package has external dependencies that may specify processing
in addition to sources (eg the UVM library specifies how to 
precompile it). I need a way to configure the toolchain that the
external packages use the toolchain defined by my package.

# Inline Specification of Inputs
The simulation tool receives its inputs and controls via task data.
This provides flexibility, by allowing multiple tasks to contribute 
command-line arguments. While I could create a new task to output
data that would add a command-line argument, I'd prefer to have
a more-direct way to do so -- a sort of inline injection of task
data that is combined with the task data of dependencies prior to
being presented to the implementation.


# Static Composition of Task Graphs (Introspection?)
I have a collection of test definitions. I want to take a selection
of them, connect my preferred simulation image, and run them.


# Static Composition of Task Graphs (Introspection)
I have collections of test definitions. I want to select tests that
have a specific attribute / tag value, connect my preferred
simulation image, and run them.



