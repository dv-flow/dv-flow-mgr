############
Installation
############

DV Flow Manager is most easily installed from the PyPI repository:

.. code-block:: bash

    % pip install dv-flow-mgr

Once installed, DV Flow Manager can be invoked using the ``dfm`` command:

.. code-block:: bash

    % dfm --help

Tool Plug-ins
=============

It is common to install additional plug-ins that provide tasks for specific
tools. For example, the ``dv-flow-libhdlsim`` package provides the tasks needed
to build and run HDL simulations:

.. code-block:: bash

    % pip install dv-flow-libhdlsim

Plug-ins are ordinary Python packages; install the ones your flow imports and
they are discovered automatically.

Next Steps
==========

* :doc:`intro` -- what DV Flow Manager is and its mental model.
* :doc:`quickstart` -- build and run your first flow.
