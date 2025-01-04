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
    
    session = Session()
    session.load(os.path.join(tmpdir, "test1"))

    out = asyncio.run(session.run("test1.files1"))
