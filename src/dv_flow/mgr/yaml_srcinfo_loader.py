
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
        mapping['srcinfo'] = {
            "file": self.filename,
            "lineno": node.start_mark.line + 1,
            "linepos": node.start_mark.column + 1
        }
        return mapping