############
Introduction
############




Many software languages have co-evolved with a build system. For example, C/C++ 
has Make and CMake. Java has ANT, Maven, and Gradle. All of these build systems
provide features that cater to specific ways that a given language is processed,
and provide built-in notions to make setting up simple cases as easy as possible.

One simple example is Make and a single-file C program. Take the code below:

.. code-block:: C
    
    #include <stdio.h>

    int main() {
        printf("Hello, world!\n");
        return 0;
    }


Make provides enough built-in features that are C/C++-specific that we can create
an executable from this source file (assume it's named hello.c) simply by running:

.. code-block:: bash

    make hello

Make knows about C files, it knows about the existance of a C compiler, and it knows
that an executable can be created from a C file of the same name.

Meanwhile, in Silicon Engineering Land...
=========================================

Much like software languages, the languages, tools, and flows used in silicon engineering
have their own unique characteristics. For example, in a silicon-design environment, many 
flows are run over the same source files -- possibly with different configurations.

* We compile our design with a UVM testbench to run dynamic (simulation-based) verification
* We compile our design with different testbenches to run formal verification
* We likely use slightly different subset when targeting synthesis

In addition, we also need to be flexible when it comes to tooling. Over time, we'll likely
use different tools from different providers, and want our projects to adapt as easily as 
possible to a change of tool. It's also likely that we will either want to add new tools
to our environment over time, or adapt our environment to take advantage of new 
productivity-enhancing tool features.

DV Flow Manager is designed to be the 'make' for silicon engineering. There are three
aspects to the tool:

* **Flow Specification** - Processing steps for a given project are captured in a hierarchy
  of YAML files. The flow-specification schema is designed to be tool-independent, such 
  that multiple tools can be implemented that comprehend a flow specification.
* **Task Library** - Processing steps are implemented as `tasks`. A library of common tasks
  is defined to cover common cases, such as creating a simulation image. External libraries
  of tasks are supported, such that tools can bundle a task library along with the tool installation.
* **Tools** - The Python implementation of DV Flow Manager is one example of a tool. Other tools
  may be added in the future to provide visualization, simplify development, etc.



Key Concepts
============

DV Flow Manager has three key concepts:
* **Package** - A packages is parameterizd namespace that contain tasks. 
* **Task** - A task is a processing step in a flow. Tasks represent a data-processing step, which
  might be as simple as building a list of files, or might be a complex as creating a hardened macro
  from multiple source collections. 
* **Dataflow Dependencies** - Tasks are related by dataflow dependencies. In order for a task to 
  execute, the data from all of its dependencies must be available. Each task also produces a 
  dataflow object that can be consumed by other tasks. 

Let's look at an example to better-understand these concepts.

.. code-block:: YAML

    package:
      name: my_ip

      imports:
      - name: hdl.sim.vlt
        as: hdl.sim

      tasks:
        - name: rtl
          uses: std.Fileset
          with:
            base: "rtl"
            include: "*.sv"

        - name: tb
          uses: std.Fileset
          needs: [rtl]
          with:
            base: "tb"
            include: "*.sv"

        - name: sim
          uses: hdl.sim.SimImage
          needs: [rtl, tb]

        -name: test1
          uses: hdl.sim.RunSim
          needs: [sim]

The code above specifies two collections of source code --
one for the design and one for the testbench. This source
code is compiled into as simulation image using the 
pre-defined task named `hdl.sim.SimImage`. After,
we execute the simulation image.


.. mermaid::

    flowchart TD
      A[rtl] --> B[tb]
      B[tb] --> E[sim]
      E --> F[test1]

The task graph for this flow is shown above. Each step depends on the
prior step, so there is no opportunity for concurrent execution.

Now, let's say that we want to run a series of tests. We can add 
a new task per tests, where we customize the activity that is run
by passing arguments to the simulation.

.. code-block:: YAML

    # ...
        -name: test1
          uses: hdl.sim.RunSim
          needs: [sim]
        -name: test2
          uses: hdl.sim.RunSim
          needs: [sim]
        -name: test3
          uses: hdl.sim.RunSim
          needs: [sim]

.. mermaid::

    flowchart TD
      A[rtl] --> B[tb]
      B[tb] --> E[sim]
      E --> F[test1]
      E --> G[test2]
      E --> H[test3]

Our task graph now looks like the above. Our build tasks are sequential,
while our test tasks only depend on the simulation image being
up-to-date, and and can execute concurrently.

## Dataflow

What ties all the tasks above together is dependency-based dataflow.

.. code-block:: YAML

        - name: tb
          uses: std.Fileset
          needs: [rtl]
          with:
            base: "tb"
            include: "*.sv"

        - name: sim
          uses: hdl.sim.SimImage
          needs: [rtl, tb]

When the `sim` task places dependencies on the `rtl` and `tb`
tasks, it receives the output from those tasks as input. In 
this case, that means that the simulation-image compilation
task has a list of all of the source files that it needs to
compile. The `sim` task also produces an output, which contains 
a reference to the directory where the simulation image resides.
The `test` tasks use this input to locate the simulation image.




