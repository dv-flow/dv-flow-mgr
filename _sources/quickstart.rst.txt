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
            params:
              include: "*.sv"

          - name: sim-image
            type: hdl.sim.SimImage
            depends: [rtl]

          - name: sim-run
            type: hdl.sim.SimRun
            depends: [sim-image]


If we run the `dvfm run` command, DV Flow Manager will:

- Find all files with a `.sv` extension in the current directory
- Compile them into a simulation image
- Run the simulation image

.. code-block:: bash

    % dvfm run

The command should complete successfully, and we should see the following