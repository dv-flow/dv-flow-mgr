import asyncio
import io
import os
import dataclasses as dc
import pytest
from typing import List
import yaml
from dv_flow.mgr import TaskData, FileSet, TaskData, TaskDataParamKindE
from pydantic import BaseModel
from shutil import copytree

def test_empty_in():

    in1 = TaskData()
    in2 = TaskData()

    out = TaskData.merge([in1, in2])

    assert len(out.params) == 0

def test_empty_combine_nonoverlap_in():

    in1 = TaskData()
    in1.setParamVal("v1", "1")
    in2 = TaskData()
    in2.setParamVal("v2", "2")

    out = TaskData.merge([in1, in2])

    assert len(out.params) != 0
    assert "v1" in out.params.keys()
    assert out.getParamVal("v1") == "1"
    assert "v2" in out.params.keys()
    assert out.getParamVal("v2") == "2"

def test_empty_combine_nonoverlap_in():

    in1 = TaskData()
    in1.setParamVal("v1", TaskDataParamKindE.String, "1")
    in2 = TaskData()
    in2.setParamVal("v2", TaskDataParamKindE.String, "2")

    out = TaskData.merge([in1, in2])

    assert len(out.params) != 0
    assert "v1" in out.params.keys()
    assert out.getParamVal("v1") == "1"
    assert "v2" in out.params.keys()
    assert out.getParamVal("v2") == "2"

def test_conflict_1():

    in1 = TaskData()
    in1.setParamVal("v1", TaskDataParamKindE.String, "1")
    in2 = TaskData()
    in2.setParamVal("v1", TaskDataParamKindE.String, "2")

    with pytest.raises(Exception):
        out = TaskData.merge([in1, in2])

def test_fileset_merge_1():
    in1 = TaskData(src="in1")
    in1.addFileSet(FileSet(
        src="in1",
        type="systemVerilogSource",
        basedir="."))

    in2 = TaskData(src="in2")
    in2.addFileSet(FileSet(
        src="in2",
        type="systemVerilogSource",
        basedir="."))

    out = TaskData.merge([in1, in2])

    assert len(out.filesets) == 2

def test_fileset_merge_common_dep_1():
    in1 = TaskData(src="in1")
    in1.addFileSet(FileSet(
        src="in1",
        type="systemVerilogSource",
        basedir="."))
    in1.addFileSet(FileSet(
        src="in0",
        type="systemVerilogSource",
        basedir="."))
    in1.deps = {
        "in1": ["in0"]
    }

    in2 = TaskData(src="in2")
    in2.addFileSet(FileSet(
        src="in1",
        type="systemVerilogSource",
        basedir="."))
    in2.addFileSet(FileSet(
        src="in2",
        type="systemVerilogSource",
        basedir="."))
    in2.addFileSet(FileSet(
        src="in0",
        type="systemVerilogSource",
        basedir="."))
    in2.deps = {
        "in1": ["in0"],
        "in2": ["in1"]
    }

    out = TaskData.merge([in2, in1])

    assert len(out.filesets) == 3
    fs = out.getFileSets(type=["systemVerilogSource"], order=True)
    assert len(fs) == 3

    assert fs[0].src == "in0"
    assert fs[1].src == "in1"
    assert fs[2].src == "in2"


