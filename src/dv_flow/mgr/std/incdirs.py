from dv_flow.mgr import TaskDataResult, TaskDataInput, TaskRunCtxt, FileSet

async def IncDirs(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """
    IncDirs - create a list of include directories
    """
    outputs = []

    for inp in input.inputs:
        if hasattr(inp, "basedir") and hasattr(inp, "filetype"):
            outputs.append(FileSet(
                filetype=inp.filetype,
                basedir=inp.basedir,
                incdirs=[inp.basedir]))
    return TaskDataResult(
        status=0,
        changed=input.changed,
        output=outputs)
