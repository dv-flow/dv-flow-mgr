import asyncio
import io
import os
import dataclasses as dc
import pytest
from typing import List
import yaml
from dv_flow_mgr import FileSet, PackageDef, Session, TaskData
from pydantic import BaseModel
from shutil import copytree

def test_fileset_1(tmpdir):
    """"""
    datadir = os.path.join(os.path.dirname(__file__), "data/fileset")

    copytree(
        os.path.join(datadir, "test1"), 
        os.path.join(tmpdir, "test1"))
    
    session = Session(os.path.join(tmpdir, "rundir"))
    session.load(os.path.join(tmpdir, "test1"))

    out = asyncio.run(session.run("test1.files1"))
    assert out.changed == True

    # Now, re-run using the same run directory.
    # Since the files haven't changed, the output must indicate that
    session = Session(os.path.join(tmpdir, "rundir"))
    session.load(os.path.join(tmpdir, "test1"))

    out = asyncio.run(session.run("test1.files1"))
    assert out.changed == False

    # Now, manually change one of the files
    with open(os.path.join(tmpdir, "test1", "files1", "file1_1.sv"), "w") as f:
        f.write("// file1_1.sv\n")

    session = Session(os.path.join(tmpdir, "rundir"))
    session.load(os.path.join(tmpdir, "test1"))

    out = asyncio.run(session.run("test1.files1"))
    assert out.changed == True
