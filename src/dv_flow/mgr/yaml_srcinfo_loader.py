
from yaml.loader import SafeLoader

class YamlSrcInfoLoader(SafeLoader):
    scopes = {
        "tasks",
        "types",
        "body",
        "package",
        "fragment"
    }

    def __init__(self, filename):
        self.filename = filename

    def __call__(self, stream):
        super().__init__(stream)
        return self

    def construct_document(self, node):
        ret = super().construct_document(node)

        # We only support srcinfo on certain elements
        if ret is not None:
            scope_s = []
            self.prune_srcinfo_dict(ret, scope_s) 

        return ret
            
    def prune_srcinfo_dict(self, ret, scope_s):
        if "srcinfo" in ret.keys() and len(scope_s) and scope_s[-1] not in YamlSrcInfoLoader.scopes:
            ret.pop('srcinfo')

        for k,v in ret.items():
            # Skip _field_srcinfo during pruning - it will be handled separately
            if k == '_field_srcinfo':
                continue
            scope_s.append(k)
            if type(v) == dict:
                self.prune_srcinfo_dict(v, scope_s)
            elif type(v) == list:
                self.prune_srcinfo_list(v, scope_s)
            scope_s.pop()

    def prune_srcinfo_list(self, ret, scope_s):
        for v in ret:
            if type(v) == dict:
                self.prune_srcinfo_dict(v, scope_s)
            elif type(v) == list:
                self.prune_srcinfo_list(v, scope_s)

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        # Add overall mapping srcinfo
        mapping['srcinfo'] = {
            "file": self.filename,
            "lineno": node.start_mark.line + 1,
            "linepos": node.start_mark.column + 1
        }
        
        # Add field-level srcinfo for better error location tracking
        mapping['_field_srcinfo'] = {}
        for key_node, value_node in node.value:
            try:
                # Construct the key to get its actual value
                key = self.construct_object(key_node, deep=False)
                if isinstance(key, str):
                    # Store the location of the value (not the key)
                    mapping['_field_srcinfo'][key] = {
                        "file": self.filename,
                        "lineno": value_node.start_mark.line + 1,
                        "linepos": value_node.start_mark.column + 1
                    }
            except:
                # If we can't construct the key, skip field-level tracking for it
                pass
        
        return mapping