
import os
import sys
import dataclasses as dc
import pytest
import importlib
from dv_flow.mgr import PyTask, PyPkg

data_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data"
)

def test_smoke(tmpdir):

    module_name = "test_pkg1"
    file_path = os.path.join(data_dir, "pytask/test_pkg1/__init__.py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Could not find module spec for {module_name} at {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # Add the module to sys.modules
    spec.loader.exec_module(module)

#    test_pkg1 = importlib.util.spec_a

    def task2(T):
        import importlib
        import inspect
        print("T: %s" % T.__qualname__)
        print("M: %s" % T.__module__)
        module = T.__module__
        elems = module.split('.')
        pkg = ".".join(elems[:-1])
        print("pkg: %s" % pkg)
        pkg_o = importlib.import_module(module)
        print("pkg_o: %s" % pkg_o)
        print("module: %s" % T.__module__)
        pkg_c = None
        T_elems = T.__qualname__.split(".")[:-1]
        if len(T_elems) > 0:
            for e in T_elems:
                print("e: %s" % e)

        for d in dir(pkg_o):
            if not d.startswith("_"):
                print("Elem: %s" % d)
                o = getattr(pkg_o, d)
                if inspect.isclass(o): # and issubclass(o, ):
                    print("isclass")
                    if pkg_c is not None:
                        raise Exception("Multiple packages: %s, %s" % (pkg_c.__name__, d))
                    pkg_c = o
        if pkg_c is None:
            raise Exception("No Package class found in %s" % pkg)
    
        return T
    
    def task(pkg):
        def _inner(T):
            print("_inner: pkg=%s" % pkg)
            return T
        return _inner

    class MyPkg(PyPkg):
        pass

    @task(MyPkg)
    class MyTask(PyTask):
        _uses_ = "std.Message"

        @dc.dataclass
        class Params(PyTask.Params):
            msg : str = "Hello World"

        

    pass