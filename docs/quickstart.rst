##########
Quickstart
##########

==========================
Installing DV Flow Manager
==========================

DV Flow Manager is most-easily installed from the PyPi repository:

.. code-block:: bash

    % pip install dv-flow-mgr


Once installed, DV Flow Mananager can be invoked using the `dvfm` command:

.. code-block:: bash

    % dvfm --help


===============
Your First Flow
===============

When starting a hardware project, it's often easy to first create a little 
compile script for the HDL sources. Over time, that script becomes larger and
larger until we realize that it's time to create a proper build system for our
design, its testbench, synthesis flows, etc.

A key goal of DV Flow Manager is to be easy enough to use that there is no need
to create the `runit.sh` shell script in the first place. We can start by creating 
a `flow.yaml` file and just continue evolving our flow definition as the project grows.

Let's create a little top-level module for our design named `top.sv`:

.. code-block:: systemverilog

    module top;
        initial begin
            $display("Hello, World!");
            $finish;
        end
    endmodule


Now, we'll create a minimal `flow.yaml` file that will allow us to compile and 
simulate this module.

.. code-block:: yaml

    package:
        name: my_design

        imports:
          - name: hdl.sim.vlt
            as: hdl.sim

        tasks:
          - name: rtl
            type: std.FileSet
            with:
              type: "systemVerilogSource"
              include: "*.sv"

          - name: sim-image
            type: hdl.sim.SimImage
            with:
              - top: [top]
            needs: [rtl]

          - name: sim-run
            type: hdl.sim.SimRun
            needs: [sim-image]


If we run the `dvfm run` command, DV Flow Manager will:

- Find all files with a `.sv` extension in the current directory
- Compile them into a simulation image
- Run the simulation image

.. code-block:: bash

    % dvfm run sim-run

This will compile the source, build a simulation image for module `top`,
and run the resulting image. Not too bad for 20-odd lines of build specification.

A Bit More Detail
=================
Let's break this down just a bit:

.. code-block:: yaml

    package:
        name: my_design

        imports:
          - name: hdl.sim.vlt
            as: hdl.sim

DV Flow Manager views the world as a series of *packages* that reference each
other and contain *tasks* to operate on sources within the *packages*.

Here, we have declared a new package (my_design) and specified that it 
references a built-in package named `hdl.sim.vlt`. This is a package that
implements tasks for performing HDL simulation with the Verilator simulator.

Note that we specify an alias (hdl.sim) for the package when importing it.
This will allow us to easily swap in a different simulator without changing
anything else within our package definition.

.. code-block:: yaml
    :highlight: 8,12

    package:
        name: my_design

        imports:
          - name: hdl.sim.vlt
            as: hdl.sim

        tasks:
          - name: rtl
            type: std.FileSet
            with:
              type: "systemVerilogSource"
              include: "*.sv"

Our first task is to specify the sources we want to process. This is done
by specifying a `FileSet` task. The parameters of this task specify where
the task should look for sources and which sources it should include