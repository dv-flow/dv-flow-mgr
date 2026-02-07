from ..task_data import TaskDataInput, TaskDataResult
from ..task_run_ctxt import TaskRunCtxt

async def DataItem(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """Generic DataItem task that creates a data item of the specified type.
    
    Parameters are extracted from input.params and passed to mkDataItem.
    Special handling for 'type' parameter which specifies the data item type,
    and 'desc' which is automatically populated from task description if not provided.
    """
    status = 0
    output = []

    # Get the type to create
    if not hasattr(input.params, 'type') or not input.params.type:
        return TaskDataResult(
            status=1,
            output=[],
            markers=[{'msg': 'Parameter "type" is required', 'severity': 'Error'}]
        )
    
    item_type = input.params.type
    
    # Collect all parameters except 'type' itself
    # Use model_dump() to get clean dictionary of fields
    kwargs = {}
    if hasattr(input.params, 'model_dump'):
        all_params = input.params.model_dump()
        for key, value in all_params.items():
            if key != 'type' and value is not None:
                kwargs[key] = value
    
    # Auto-populate desc from task description if not explicitly provided
    if 'desc' not in kwargs or not kwargs['desc']:
        task_desc = getattr(input, 'desc', '') or ''
        if task_desc:
            kwargs['desc'] = task_desc
    
    # Create the data item
    item = ctxt.mkDataItem(type=item_type, **kwargs)
    output.append(item)

    return TaskDataResult(
        status=status,
        output=output
    )



