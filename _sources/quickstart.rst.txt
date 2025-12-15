##########
Quickstart
##########

==========================
Installing DV Flow Manager
==========================

DV Flow Manager is most-easily installed from the PyPi repository:

.. code-block:: bash

    % pip install dv-flow-mgr


Once installed, DV Flow Mananager can be invoked using the `dfm` command:

.. code-block:: bash

    % dfm --help

It's common to install other plugin-ins to support various tools. The example
below builds and runs a Verilog module. The `dv-flow-libhdlsim` package 
provides the required tasks:

.. code-block:: bash

    % pip install dv-flow-libhdlsim


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

        tasks:
          - name: rtl
            type: std.FileSet
            with:
              type: "systemVerilogSource"
              include: "*.sv"

          - name: sim-image
            type: hdlsim.vlt.SimImage
            with:
              - top: [top]
            needs: [rtl]

          - name: sim-run
            type: hdlsim.vlt.SimRun
            needs: [sim-image]


If we run the `dfm run` command, DV Flow Manager will:

- Find all files with a `.sv` extension in the current directory
- Compile them into a simulation image
- Run the simulation image

.. code-block:: bash

    % dfm run sim-run

This will compile the source, build a simulation image for module `top`,
and run the resulting image. Not too bad for 20-odd lines of build specification.

A Bit More Detail
=================
Let's break this down just a bit:

.. code-block:: yaml

    package:
        name: my_design

DV Flow Manager views the world as a series of *packages* that reference each
other and contain *tasks* to operate on sources within the *packages*.

.. code-block:: yaml
    :emphasize-lines: 8,12

    package:
        name: my_design

        tasks:
          - name: rtl
            type: std.FileSet
            with:
              type: "systemVerilogSource"
              include: "*.sv"

Our first task is to specify the sources we want to process. This is done
by specifying a `FileSet` task. The parameters of this task specify where
the task should look for sources and which sources it should include.

.. code-block:: yaml
    :emphasize-lines: 5,6

    package:
        name: my_design

        tasks:
          - name: sim-image
            type: hdlsim.vlt.SimImage
            with:
              - top: [top]
            needs: [rtl]

The second task creates a simulation image using the Verilator simulator.
The `type` field references the `hdlsim.vlt.SimImage` task from the 
`dv-flow-libhdlsim` package. The `with` section specifies that `top` is the
top-level module. The `needs` field declares that this task depends on the 
`rtl` task, ensuring the source files are collected before compilation.

.. code-block:: yaml
    :emphasize-lines: 5,6

    package:
        name: my_design

        tasks:
          - name: sim-run
            type: hdlsim.vlt.SimRun
            needs: [sim-image]

The third task runs the simulation. It uses the `hdlsim.vlt.SimRun` task type
and depends on the `sim-image` task. When executed, this task will run the
compiled simulation image and produce the "Hello, World!" output.