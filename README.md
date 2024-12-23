# dv-flow-mgr
Flow manager for design and verification projects

DV Flow Manager (dvfm) is a flow manager that focuses on the unique requirements
of hardware design and verification flows. 

# Key Concepts

A flow is composed of tasks connected by data objects. Data objects can contain
arbitrary parameters (key/value pairs) and a list of filesets. The dependency 
tree of filesets is maintained, such that consumers can create a flat list
of files in proper order or do something more intelligent by partitioning 
the tree.

Projects and other units of functionality are encapsulated as "packages". A 
package has a public persona, defined by:
- Exported flows intended for use by higher-level packages
- Flows intended for use while developing the package, and not visible to higher-level packages
  (ie are private to the package)
- Subflows that are only visible within the package (ie are private to the package)

Packages, Flows, and SubFlows are considered to be types, and support inheritance
and extension relationships.

There are two levels of schema definition for a .flow file:
- The .flow file has a schema, which defines the key elements in the file
- Types (package, flow, subflow) define schemas for their respective 
  bodies that define what content is permitted.

# Package
- Packages support inheritance relationships
- Packages can define parameters that are specified when the package is referenced
- Each parameterization  

# Flow
- Flows are top-level elements within packages. They can 

# Subflow
- Files that define subflows must be imported from within the scope of a package. 
  In other words, subflows 
- Subflows have 0+ inputs and produce 1+ outputs
  - Inputs are specified by '



