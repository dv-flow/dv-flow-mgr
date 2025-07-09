from dv_flow.mgr import TaskDataResult, TaskDataInput, TaskRunCtxt

async def SetFileType(ctxt: TaskRunCtxt, inputs: TaskDataInput) -> TaskDataResult:
    output = []

    for inp in inputs.inputs:
        if inp.type == "std.FileSet":
            inp = inp.copy()
            inp.filetype = inputs.params.filetype
            inp.src = None
            inp.seq = -1
            output.append(inp)

    return TaskDataResult(
        changed=inputs.changed,
        output=output,
        status=0
    )
