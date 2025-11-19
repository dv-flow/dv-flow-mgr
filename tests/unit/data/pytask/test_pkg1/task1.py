import dataclasses as dc
from .test_pkg1 import TestPkg1, TestPkg2
from dv_flow.mgr import PyTask, pytask

# def task(T):
#     import importlib
#     import inspect
#     module = T.__module__
#     elems = module.split('.')
#     pkg = ".".join(elems[:-1])
#     print("pkg: %s" % pkg)
#     pkg_o = importlib.import_module(pkg)
#     print("pkg_o: %s" % pkg_o)
#     print("module: %s" % T.__module__)
#     pkg_c = None
#     for d in dir(pkg_o):
#         if not d.startswith("_"):
#             print("Elem: %s" % d)
#             o = getattr(pkg_o, d)
#             if inspect.isclass(o): # and issubclass(o, ):
#                 print("isclass")
#                 if pkg_c is not None:
#                     raise Exception("Multiple packages: %s, %s" % (pkg_c.__name__, d))
#                 pkg_c = o
#     if pkg_c is None:
#         raise Exception("No Package class found in %s" % pkg)

#     return T

# def task(pkg):
#     def _inner(T):
#         print("_inner: pkg=%s" % pkg)
#         pkg.registerTask(T)
#         return T
#     return _inner

@pytask(TestPkg1)
class Task1(PyTask):

    @dc.dataclass
    class Params(PyTask.Params):
        a : int = dc.field(default=5, metadata=dict(desc="Hello"))
        pass

    async def __call__(self):
        pass
    pass

@pytask(TestPkg1)
class Task2(PyTask):

    @dc.dataclass
    class Params(Task1.Params):
        a : int = dc.field(default=6,
                           metadata=dict(
                               desc="""ABC""",
                           ))
        pass

    run = "abc"

#    async def run(self):
#        self.params.a
        
