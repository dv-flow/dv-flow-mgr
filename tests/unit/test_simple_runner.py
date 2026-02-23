"""Simple test to debug TaskSetRunner initialization"""
from dv_flow.mgr.task_runner import TaskSetRunner


def test_simple_runner_creation(tmpdir):
    """Test that TaskSetRunner creates jobserver"""
    print("About to create TaskSetRunner")
    runner = TaskSetRunner(str(tmpdir / "rundir"), nproc=4)
    print(f"Created runner")
    print(f"Has _jobserver: {hasattr(runner, '_jobserver')}")
    if hasattr(runner, '_jobserver'):
        print(f"_jobserver: {runner._jobserver}")
        print(f"MAKEFLAGS: {runner.env.get('MAKEFLAGS')}")
        if runner._jobserver:
            runner._jobserver.close()
    
    assert hasattr(runner, '_jobserver'), "Runner should have _jobserver attribute"
    assert runner._jobserver is not None, "Jobserver should be created"
