
import json
import os
import sys
from pydantic import BaseModel
import pydantic.dataclasses as pdc
from typing import Union
from ...fragment_def import FragmentDef
from ...package_def import PackageDef

class DvFlowSchema(BaseModel):
    root : Union[PackageDef,FragmentDef] = pdc.Field(default=None)

class CmdSchema(object):
    """Generate JSON Schema for DV Flow definitions.
    
    By default, emits the canonical schema from dv.flow.schema.json.
    Use --generate to regenerate from Pydantic models (development mode).
    """
    
    # Implementation artifacts to exclude from user-facing schema
    EXCLUDE_DEFS = {
        'SrcInfo',           # Internal source location tracking
        'PackageSpec',       # Internal package specification
        'TaskBodyDef',       # Internal task body structure
        'TasksBuilder',      # Internal builder
        'Tasks',             # Internal wrapper
        'NeedSpec',          # Internal need specification
        'TaskSpec',          # Internal task specification
    }
    
    def _filter_srcinfo_from_properties(self, props):
        """Remove srcinfo field from properties dict."""
        if 'srcinfo' in props:
            del props['srcinfo']
        return props
    
    def _referenced_defs(self, node, out=None):
        """Every `#/defs/<Name>` reachable from `node`."""
        if out is None:
            out = set()
        if isinstance(node, dict):
            ref = node.get('$ref')
            if isinstance(ref, str) and ref.startswith('#/defs/'):
                out.add(ref[len('#/defs/'):])
            for value in node.values():
                self._referenced_defs(value, out)
        elif isinstance(node, list):
            for value in node:
                self._referenced_defs(value, out)
        return out

    def _filter_implementation_artifacts(self, defs):
        """Remove implementation artifacts from schema definitions.

        A definition is only dropped when nothing still points at it. Dropping
        a *referenced* one leaves a `$ref` resolving to nothing, which makes the
        published schema invalid -- every strict validator fails on it, and the
        editors that consume it via `# yaml-language-server: $schema=...` report
        an error on the file rather than completing it.

        `PackageDef.type` is the case that found this: it is annotated
        `List[PackageSpec]`, `PackageSpec` is excluded here, and the resulting
        schema shipped with a dangling reference. Keeping it is the conservative
        repair -- it is also more honest, since an internal type appearing in
        the public schema is a visible prompt to fix the annotation, where a
        broken reference merely looks like a rendering glitch.
        """
        # Strip `srcinfo` properties FIRST. They are the only thing that
        # references `SrcInfo`, so computing reachability before removing them
        # would find it still referenced and keep it -- putting the internal
        # type back into the schema that this filter exists to take it out of.
        for def_name, def_schema in defs.items():
            if 'properties' in def_schema:
                self._filter_srcinfo_from_properties(def_schema['properties'])

        keep = self._referenced_defs(defs)

        for exclude in self.EXCLUDE_DEFS:
            if exclude in defs and exclude not in keep:
                del defs[exclude]

        return defs

    def _generate_schema(self):
        """Generate schema from Pydantic models."""
        root_s = DvFlowSchema.model_json_schema(
            ref_template="#/defs/{model}"
        )

        defs = {}
        defs.update(root_s["$defs"])

        # Filter out implementation artifacts
        defs = self._filter_implementation_artifacts(defs)

        # Add target markers for each definition
        for td in defs.keys():
            defs[td]["$$target"] = "#/defs/%s" % td

        root = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://dv-flow.github.io/dv.flow.schema.json",
            "title": "DV Flow specification schema",
            "description": "JSON Schema for DV Flow YAML workflow definitions",
            "type": "object",
            "oneOf": [
                {
                    "properties": {
                        "package": {
                            "$ref": "#/defs/PackageDef",
                            "title": "Package Definition",
                            "description": "Root package definition for a DV Flow project"
                        }
                    },
                    "required": ["package"]
                },
                {
                    "properties": {
                        "fragment": {
                            "$ref": "#/defs/FragmentDef",
                            "title": "Fragment Definition",
                            "description": "Reusable fragment containing tasks, types, and imports"
                        }
                    },
                    "required": ["fragment"]
                }
            ],
            "defs": defs,
        }
        
        return root

    def _load_canonical_schema(self):
        """Load the canonical schema file."""
        # Get path to schema file in share directory
        import dv_flow.mgr
        pkg_dir = os.path.dirname(os.path.abspath(dv_flow.mgr.__file__))
        schema_path = os.path.join(pkg_dir, "share", "dv.flow.schema.json")
        
        if not os.path.exists(schema_path):
            raise FileNotFoundError(
                f"Canonical schema not found at {schema_path}. "
                "Run 'dfm util schema --generate' to create it."
            )
        
        with open(schema_path, 'r') as f:
            return json.load(f)

    def __call__(self, args):
        if args.output == "-":
            fp = sys.stdout
        else:
            fp = open(args.output, "w")

        # Generate schema from Pydantic models if requested
        if hasattr(args, 'generate') and args.generate:
            schema = self._generate_schema()
        else:
            # Try to load canonical schema, fall back to generation
            try:
                schema = self._load_canonical_schema()
            except FileNotFoundError as e:
                print(f"Warning: {e}", file=sys.stderr)
                print("Generating from Pydantic models...", file=sys.stderr)
                schema = self._generate_schema()

        fp.write(json.dumps(schema, indent=2))
        fp.write('\n')

        if fp != sys.stdout:
            fp.close()
