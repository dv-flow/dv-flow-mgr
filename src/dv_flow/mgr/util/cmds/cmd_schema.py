
import json
import sys
from pydantic import BaseModel
import pydantic.dataclasses as pdc
from typing import Union
from ...fragment_def import FragmentDef
from ...package_def import PackageDef

class DvFlowSchema(BaseModel):
    root : Union[PackageDef,FragmentDef] = pdc.Field(default=None)

class CmdSchema(object):

    def __call__(self, args):
        if args.output == "-":
            fp = sys.stdout
        else:
            fp = open(args.output, "w")

        root_s = DvFlowSchema.model_json_schema(
            ref_template="#/defs/{model}"
        )
        pkg_s = PackageDef.model_json_schema(
            ref_template="#/defs/{model}"
        )
        frag_s = FragmentDef.model_json_schema(
            ref_template="#/defs/{model}"
        )

        defs = {}
        defs.update(root_s["$defs"])
#        defs.update(pkg_s["$defs"])
#        defs.update(frag_s["$defs"])

        for td in defs.keys():
            defs[td]["$$target"] = "#/defs/%s" % td

        root = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://dv-flow.github.io/flow.dv.schema.json",
            "title": "DV Flow-specification schema",
            "description": "Flow-specification schema",
            "type": "object",
            "properties": {
                "package": {
                    "$ref": "#/defs/PackageDef",
                    "title": "Package Definition",
                    "description": "Package Definition"
                },
                "fragment": {
                    "$ref": "#/defs/FragmentDef"
                }
            },
            "defs": defs,
        }

        fp.write(json.dumps(root, indent=2))

        if fp != sys.stdout:
            fp.close()
