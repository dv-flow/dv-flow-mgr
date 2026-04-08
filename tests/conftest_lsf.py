"""LSF test infrastructure: markers, options, fixtures."""
import os
import shutil
import pytest
from dv_flow.mgr.runner_config import LsfConfig, RunnerConfig


def pytest_addoption(parser):
    """Register LSF-specific command-line options."""
    group = parser.getgroup("lsf", "LSF integration test options")
    group.addoption("--lsf-bsub-cmd", default=None,
                    help="bsub command name (default: bsub)")
    group.addoption("--lsf-queue", default=None,
                    help="LSF queue for test jobs (required for system tests)")
    group.addoption("--lsf-project", default=None,
                    help="LSF -P project string")
    group.addoption("--lsf-resource-select", default=None,
                    help="-R select[...] predicate")
    group.addoption("--lsf-dfm-path", default=None,
                    help="Path to dfm binary on compute nodes")
    group.addoption("--lsf-bsub-extra", default=None,
                    help="Extra bsub flags (comma-separated)")


def _opt(request, cli_name, env_name, default=None):
    """Resolve option: CLI flag > env var > default."""
    val = request.config.getoption(cli_name, default=None)
    if val is None:
        val = os.environ.get(env_name)
    return val if val is not None else default


requires_lsf = pytest.mark.skipif(
    shutil.which("bsub") is None and shutil.which("lsf_bsub") is None,
    reason="LSF tools not available (checked bsub and lsf_bsub)"
)


@pytest.fixture
def lsf_available():
    """Skip test if LSF is not available."""
    if shutil.which("bsub") is None and shutil.which("lsf_bsub") is None:
        pytest.skip("LSF not available")


@pytest.fixture
def lsf_config(request):
    """Build an LsfConfig from pytest options / env vars."""
    bsub_cmd = _opt(request, "--lsf-bsub-cmd",
                    "DFM_TEST_LSF_BSUB_CMD", "bsub")
    queue = _opt(request, "--lsf-queue", "DFM_TEST_LSF_QUEUE")
    project = _opt(request, "--lsf-project",
                   "DFM_TEST_LSF_PROJECT", "")
    resource_select_str = _opt(request, "--lsf-resource-select",
                               "DFM_TEST_LSF_RESOURCE_SELECT")
    dfm_path = _opt(request, "--lsf-dfm-path",
                    "DFM_TEST_LSF_DFM_PATH", "dfm")
    bsub_extra_str = _opt(request, "--lsf-bsub-extra",
                          "DFM_TEST_LSF_BSUB_EXTRA")

    if not queue:
        pytest.skip(
            "LSF system tests require --lsf-queue or "
            "DFM_TEST_LSF_QUEUE to be set"
        )

    resource_select = (
        [s.strip() for s in resource_select_str.split(",")]
        if resource_select_str else []
    )
    bsub_extra = (
        [s.strip() for s in bsub_extra_str.split(",")]
        if bsub_extra_str else []
    )

    return LsfConfig(
        bsub_cmd=bsub_cmd,
        queue=queue,
        project=project,
        resource_select=resource_select,
        bsub_extra=bsub_extra,
        worker_dfm_path=dfm_path,
    )


@pytest.fixture
def lsf_runner_config(lsf_config):
    """Full RunnerConfig with LSF settings from test options."""
    return RunnerConfig(type="lsf", lsf=lsf_config)
