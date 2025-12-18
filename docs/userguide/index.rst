##########
User Guide
##########

.. toctree::
   :maxdepth: 1

   fundamentals
   packages
   tasks_using
   tasks_developing
   configuration
   stdlib

DV Flow input specification builds on three key concepts:

* **Package** - A packages is a parameterized namespace that defines tasks and types.
* **Task** - A task is a processing step in a flow. Tasks represent a data-processing step, which
  might be as simple as building a list of files, or might be a complex as creating a hardened macro
  from multiple source collections. 
* **Dataflow Dependencies** - Tasks are related by dataflow dependencies. In order for a task to 
  execute, the data from all of its dependencies must be available. Each task also produces 
  dataflow items that can be consumed by other tasks. 

The execution graph of a root task (or tasks) and its dependencies is statically known.
The precise data conveyed between tasks via dataflow is only known at runtime.

Let's look at an example to better-understand these concepts.

.. code-block:: YAML

    package:
      name: my_ip
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
          uses: hdlsim.vlt.SimImage
          needs: [rtl, tb]

        -name: test1
          uses: hdlsim.vlt.RunSim
          needs: [sim]

The code above specifies two collections of source code --
one for the design and one for the testbench. This source
code is compiled into as simulation image using the 
pre-defined task named `hdlsim.vlt.SimImage`. After,
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
          uses: hdlsim.vlt.RunSim
          needs: [sim]
        -name: test2
          uses: hdlsim.vlt.RunSim
          needs: [sim]
        -name: test3
          uses: hdlsim.vlt.RunSim
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

Dataflow
--------

What ties all the tasks above together is dependency-based dataflow.

.. code-block:: YAML

        - name: tb
          uses: std.Fileset
          needs: [rtl]
          with:
            base: "tb"
            include: "*.sv"

        - name: sim
          uses: hdlsim.vlt.SimImage
          needs: [rtl, tb]

When the `sim` task places dependencies on the `rtl` and `tb`
tasks, it receives the output from those tasks as input. In 
this case, that means that the simulation-image compilation
task has a list of all of the source files that it needs to
compile. The `sim` task also produces an output, which contains 
a reference to the directory where the simulation image resides.
The `test` tasks use this input to locate the simulation image.

